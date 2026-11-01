from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api.routers import rate_limit
from src.api.routers.rate_limit import check_rate_limit

pytestmark = pytest.mark.unit


class FakePipeline:
    def __init__(self, results=None, error=None):
        self.results = results
        self.error = error
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def set(self, *args, **kwargs):
        self.calls.append(("set", args, kwargs))

    def incr(self, *args, **kwargs):
        self.calls.append(("incr", args, kwargs))

    def ttl(self, *args, **kwargs):
        self.calls.append(("ttl", args, kwargs))

    async def execute(self):
        if self.error:
            raise self.error
        return self.results


class FakeRedis:
    def __init__(self, pipe):
        self.pipe = pipe
        self.transaction = None

    def pipeline(self, transaction=True):
        self.transaction = transaction
        return self.pipe


class TestCheckRateLimit:
    async def test_allows_request_under_limit(self):
        pipe = FakePipeline(results=[True, 1, 60])
        redis = FakeRedis(pipe)

        await check_rate_limit(redis, "k", limit=5, window_seconds=60)

        assert redis.transaction is True
        assert pipe.calls == [
            ("set", ("k", 0), {"ex": 60, "nx": True}),
            ("incr", ("k",), {}),
            ("ttl", ("k",), {}),
        ]

    async def test_allows_request_exactly_at_limit(self):
        await check_rate_limit(FakeRedis(FakePipeline(results=[True, 5, 60])), "k", 5, 60)

    async def test_blocks_request_over_limit_with_retry_after(self):
        redis = FakeRedis(FakePipeline(results=[True, 6, 42]))

        with pytest.raises(HTTPException) as exc:
            await check_rate_limit(redis, "k", limit=5, window_seconds=60)

        assert exc.value.status_code == 429
        assert exc.value.headers == {"Retry-After": "42"}

    @pytest.mark.parametrize("ttl", [-1, -2, 0])
    async def test_retry_after_is_at_least_one_second(self, ttl):
        redis = FakeRedis(FakePipeline(results=[True, 99, ttl]))

        with pytest.raises(HTTPException) as exc:
            await check_rate_limit(redis, "k", 5, 60)

        assert exc.value.headers == {"Retry-After": "1"}

    async def test_fails_open_when_redis_errors_on_execute(self):
        redis = FakeRedis(FakePipeline(error=ConnectionError("redis down")))

        await check_rate_limit(redis, "k", 1, 60)

    async def test_fails_open_when_pipeline_cannot_be_created(self):
        redis = SimpleNamespace(pipeline=lambda **kw: (_ for _ in ()).throw(OSError("boom")))

        await check_rate_limit(redis, "k", 1, 60)


class TestEnforcers:
    @pytest.fixture
    def check(self, monkeypatch):
        mock = AsyncMock()
        monkeypatch.setattr(rate_limit, "check_rate_limit", mock)
        return mock

    async def test_hint_limit_uses_defaults(self, monkeypatch, check):
        monkeypatch.setattr(rate_limit, "settings", SimpleNamespace())

        await rate_limit.enforce_hint_rate_limit(actor=SimpleNamespace(id=7), redis="r")

        check.assert_awaited_once_with("r", "ratelimit:hint:7", 20, 3600)

    async def test_hint_limit_can_be_configured(self, monkeypatch, check):
        monkeypatch.setattr(
            rate_limit, "settings", SimpleNamespace(HINT_RATE_LIMIT_PER_HOUR=3)
        )

        await rate_limit.enforce_hint_rate_limit(actor=SimpleNamespace(id=7), redis="r")

        check.assert_awaited_once_with("r", "ratelimit:hint:7", 3, 3600)

    async def test_draft_limit_uses_defaults(self, monkeypatch, check):
        monkeypatch.setattr(rate_limit, "settings", SimpleNamespace())

        await rate_limit.enforce_draft_rate_limit(actor=SimpleNamespace(id=9), redis="r")

        check.assert_awaited_once_with("r", "ratelimit:draft:9", 5, 3600)

    async def test_draft_limit_can_be_configured(self, monkeypatch, check):
        monkeypatch.setattr(
            rate_limit, "settings", SimpleNamespace(DRAFT_RATE_LIMIT_PER_HOUR=1)
        )

        await rate_limit.enforce_draft_rate_limit(actor=SimpleNamespace(id=9), redis="r")

        check.assert_awaited_once_with("r", "ratelimit:draft:9", 1, 3600)

    async def test_limits_are_tracked_per_user_and_per_feature(self, monkeypatch, check):
        monkeypatch.setattr(rate_limit, "settings", SimpleNamespace())

        await rate_limit.enforce_hint_rate_limit(actor=SimpleNamespace(id=1), redis="r")
        await rate_limit.enforce_hint_rate_limit(actor=SimpleNamespace(id=2), redis="r")
        await rate_limit.enforce_draft_rate_limit(actor=SimpleNamespace(id=1), redis="r")

        keys = [c.args[1] for c in check.await_args_list]
        assert len(set(keys)) == 3