from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.session_per_call import PerCallRepository, per_call


class FakeRepo:
    instances: list = []

    def __init__(self, session):
        self.session = session
        FakeRepo.instances.append(self)

    async def add(self, a, b=0):
        return a + b

    async def explode(self):
        raise RuntimeError("boom")

    def plain(self):
        return "sync"

    attribute = "not callable"


@pytest.fixture(autouse=True)
def reset_instances():
    FakeRepo.instances = []


@pytest.fixture
def sessions():
    return []


@pytest.fixture
def events():
    return []


@pytest.fixture
def session_factory(sessions, events):
    @asynccontextmanager
    async def factory():
        session = MagicMock()

        async def commit():
            events.append("commit")

        session.commit = AsyncMock(side_effect=commit)
        sessions.append(session)
        events.append("open")
        try:
            yield session
        finally:
            events.append("close")

    return factory


@pytest.fixture
def repo(session_factory):
    return per_call(FakeRepo, session_factory)


class TestPerCall:

    def test_per_call_returns_per_call_repository(self, repo):
        assert isinstance(repo, PerCallRepository)

    async def test_forwards_args_and_returns_result(self, repo):
        assert await repo.add(1, b=2) == 3
        assert await repo.add(5) == 5

    async def test_commits_after_the_call_inside_the_session(self, repo, events):
        await repo.add(1)

        assert events == ["open", "commit", "close"]

    async def test_uses_a_fresh_session_and_repo_per_call(self, repo, sessions):
        await repo.add(1)
        await repo.add(2)

        assert len(sessions) == 2
        assert sessions[0] is not sessions[1]
        assert [i.session for i in FakeRepo.instances] == sessions

    async def test_does_not_commit_when_the_call_fails(self, repo, sessions, events):
        with pytest.raises(RuntimeError, match="boom"):
            await repo.explode()

        sessions[0].commit.assert_not_called()
        assert events == ["open", "close"]

    async def test_wrapper_keeps_method_name(self, repo):
        assert repo.add.__name__ == "add"

    def test_sync_method_is_rejected(self, repo):
        with pytest.raises(AttributeError, match="async"):
            repo.plain

    def test_non_callable_attribute_is_rejected(self, repo):
        with pytest.raises(AttributeError):
            repo.attribute

    def test_unknown_method_is_rejected(self, repo):
        with pytest.raises(AttributeError):
            repo.missing

    def test_private_names_are_not_proxied(self, repo):
        with pytest.raises(AttributeError):
            repo._anything

    def test_does_not_open_a_session_just_by_accessing_a_method(
        self, repo, sessions
    ):
        repo.add

        assert sessions == []