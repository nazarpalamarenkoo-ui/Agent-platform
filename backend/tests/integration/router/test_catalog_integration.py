"""POST /catalog/hint together with its Redis-backed rate limiter."""
from unittest.mock import AsyncMock

import pytest

from src.api.auth import auth as main_auth
from src.api.auth.admin import auth as admin_auth
from src.api.routers import catalog, rate_limit
from src.catalog.hint.catalog_hint_service import CatalogHintService
from src.catalog.hint.exceptions import (
    HintClientError,
    HintError,
    HintParseError,
    HintValidationError,
)
from src.config import settings
from src.db.db_connection import get_db
from src.dependencies import get_arq_pool, get_catalog_hint_service
from src.schemas.catalog import HintItem, HintProfile, HintRef, HintResponse
from src.services.errors import NotFoundError

pytestmark = [pytest.mark.integration, pytest.mark.db]

HINT_LIMIT = getattr(settings, "HINT_RATE_LIMIT_PER_HOUR", rate_limit.HINT_DEFAULT_LIMIT)


class FakePipeline:
    def __init__(self, store):
        self._store = store
        self._ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def set(self, key, value, ex=None, nx=False):
        self._ops.append(("set", key, value, ex, nx))

    def incr(self, key):
        self._ops.append(("incr", key))

    def ttl(self, key):
        self._ops.append(("ttl", key))

    async def execute(self):
        results = []
        for op, key, *rest in self._ops:
            if op == "set":
                value, ex, nx = rest
                if nx and key in self._store:
                    results.append(None)
                else:
                    self._store[key] = {"value": value, "ttl": ex}
                    results.append(True)
            elif op == "incr":
                self._store[key]["value"] += 1
                results.append(self._store[key]["value"])
            else:
                results.append(self._store[key]["ttl"])
        return results


class FakeRedis:
    def __init__(self):
        self.store = {}

    def pipeline(self, transaction=True):
        return FakePipeline(self.store)


class BrokenRedis:
    def pipeline(self, transaction=True):
        raise ConnectionError("redis is down")


@pytest.fixture
def redis():
    return FakeRedis()


@pytest.fixture
def hint_service():
    service = AsyncMock(spec=CatalogHintService)
    service.propose.return_value = HintResponse()
    return service


@pytest.fixture
def app(db_session, build_app, hint_service, redis):
    application = build_app(catalog.router)
    application.dependency_overrides[get_db] = lambda: db_session
    application.dependency_overrides[get_catalog_hint_service] = lambda: hint_service
    application.dependency_overrides[get_arq_pool] = lambda: redis
    return application


@pytest.fixture
def login(app):
    def _login(user):
        for dependency in (main_auth.get_current_user, admin_auth.get_current_user):
            app.dependency_overrides[dependency] = lambda: user
        return user

    return _login


@pytest.fixture
def me(sample_user, login):
    return login(sample_user)


def counter_key(user):
    return f"ratelimit:hint:{user.id}"


async def hint(client, intent="build an api for orders"):
    return await client.post("/catalog/hint", json={"intent": intent})


# --- authentication / validation ---


async def test_hint_requires_authentication(client, hint_service):
    response = await client.post("/catalog/hint", json={"intent": "anything"})

    assert response.status_code == 401, response.text
    hint_service.propose.assert_not_awaited()


@pytest.mark.parametrize("intent", ["", "   ", "x" * 1001])
async def test_hint_invalid_intent_returns_422(client, me, hint_service, intent):
    response = await hint(client, intent)

    assert response.status_code == 422, response.text
    hint_service.propose.assert_not_awaited()


async def test_hint_without_intent_returns_422(client, me):
    response = await client.post("/catalog/hint", json={})

    assert response.status_code == 422, response.text


# --- happy path ---


async def test_hint_returns_service_proposal(client, me, hint_service):
    hint_service.propose.return_value = HintResponse(
        agent_profile=HintProfile(
            id=1,
            name="backend-agent",
            description="Backend helper",
            base_skills=[HintRef(id=2, name="code-review")],
            base_tools=[HintRef(id=3, name="web_search")],
        ),
        skills=[HintItem(id=4, name="summarization", description="Summarize text")],
        tools=[HintItem(id=5, name="calculator")],
        knowledge_packs=[HintItem(id=6, name="API pack")],
        reasoning="because",
    )

    response = await hint(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent_profile"]["name"] == "backend-agent"
    assert body["agent_profile"]["base_skills"] == [{"id": 2, "name": "code-review"}]
    assert [item["id"] for item in body["skills"]] == [4]
    assert [item["id"] for item in body["tools"]] == [5]
    assert [item["id"] for item in body["knowledge_packs"]] == [6]
    assert body["reasoning"] == "because"


async def test_hint_empty_proposal_has_defaults(client, me):
    response = await hint(client)

    assert response.json() == {
        "agent_profile": None,
        "skills": [],
        "tools": [],
        "knowledge_packs": [],
        "reasoning": "",
    }


async def test_hint_passes_viewer_and_stripped_intent_to_service(client, me, hint_service):
    await hint(client, "  build an api  ")

    hint_service.propose.assert_awaited_once_with(viewer_id=me.id, intent="build an api")


# --- error mapping ---


@pytest.mark.parametrize(
    "error, expected",
    [
        (HintClientError("llm boom"), 503),
        (HintValidationError("bad json boom"), 502),
        (HintParseError("parse boom"), 502),
        (HintError("generic boom"), 500),
    ],
)
async def test_hint_errors_are_mapped_without_leaking_internals(client, me, hint_service, error, expected):
    hint_service.propose.side_effect = error

    response = await hint(client)

    assert response.status_code == expected, response.text
    assert "boom" not in response.text


@pytest.mark.parametrize(
    "error, expected",
    [(NotFoundError("Agent not found"), 404), (ValueError("bad intent"), 400)],
)
async def test_hint_value_errors_are_mapped(client, me, hint_service, error, expected):
    hint_service.propose.side_effect = error

    response = await hint(client)

    assert response.status_code == expected, response.text
    assert response.json()["detail"] == str(error)


# --- rate limiting ---


async def test_hint_counts_requests_per_user(client, me, redis):
    await hint(client)
    await hint(client)

    assert redis.store[counter_key(me)]["value"] == 2
    assert redis.store[counter_key(me)]["ttl"] == rate_limit.HINT_WINDOW_SECONDS


async def test_hint_last_allowed_request_passes_and_next_is_blocked(client, me, redis, hint_service):
    redis.store[counter_key(me)] = {"value": HINT_LIMIT - 1, "ttl": 120}

    allowed = await hint(client)
    blocked = await hint(client)

    assert allowed.status_code == 200, allowed.text
    assert blocked.status_code == 429, blocked.text
    assert hint_service.propose.await_count == 1


async def test_hint_over_limit_returns_429_with_retry_after(client, me, redis, hint_service):
    redis.store[counter_key(me)] = {"value": HINT_LIMIT, "ttl": 120}

    response = await hint(client)

    assert response.status_code == 429, response.text
    assert response.headers["retry-after"] == "120"
    hint_service.propose.assert_not_awaited()


async def test_hint_retry_after_is_at_least_one_second(client, me, redis):
    redis.store[counter_key(me)] = {"value": HINT_LIMIT, "ttl": -1}

    response = await hint(client)

    assert response.status_code == 429, response.text
    assert response.headers["retry-after"] == "1"


async def test_hint_rate_limit_is_per_user(client, login, sample_user, another_user, redis):
    redis.store[counter_key(sample_user)] = {"value": HINT_LIMIT, "ttl": 120}
    login(sample_user)
    assert (await hint(client)).status_code == 429

    login(another_user)
    response = await hint(client)

    assert response.status_code == 200, response.text


async def test_hint_fails_open_when_redis_is_unavailable(app, client, me, hint_service):
    app.dependency_overrides[get_arq_pool] = lambda: BrokenRedis()

    response = await hint(client)

    assert response.status_code == 200, response.text
    hint_service.propose.assert_awaited_once()