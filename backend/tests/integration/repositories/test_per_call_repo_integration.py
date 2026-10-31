import pytest
from sqlalchemy.exc import IntegrityError

from src.repositories.session_per_call import PerCallRepository, per_call
from src.repositories.tag_repo import TagRepository

pytestmark = pytest.mark.integration


class CountingFactory:
    """Wraps the test session factory and records how often it was opened."""

    def __init__(self, inner):
        self._inner = inner
        self.opened = 0

    def __call__(self):
        self.opened += 1
        return self._inner()


@pytest.fixture
def factory(db_session):
    return CountingFactory(db_session)


@pytest.fixture
def tags(factory):
    return per_call(TagRepository, factory)


class TestPerCallExecution:

    async def test_per_call_returns_a_per_call_repository(self, factory):
        assert isinstance(per_call(TagRepository, factory), PerCallRepository)

    async def test_result_of_the_repo_method_is_returned(self, tags):
        tag = await tags.create(tag_name="per-call-tag")

        assert tag.id is not None
        assert tag.tag_name == "per-call-tag"

    async def test_each_call_opens_its_own_session(self, tags, factory):
        await tags.create(tag_name="first")
        await tags.get_by_name("first")
        await tags.get_by_name("missing")

        assert factory.opened == 3

    async def test_each_call_commits_so_later_calls_see_the_data(self, tags, db_session):
        created = await tags.create(tag_name="committed")

        found = await tags.get_by_name("committed")

        assert found is not None
        assert found.id == created.id

    async def test_commit_is_issued_after_every_call(self, tags, db_session, monkeypatch):
        commits = []
        real_commit = db_session.commit

        async def spy():
            commits.append(1)
            await real_commit()

        monkeypatch.setattr(db_session._session, "commit", spy)

        await tags.create(tag_name="spied")
        await tags.get_by_name("spied")

        assert len(commits) == 2

    async def test_get_or_create_is_idempotent_across_calls(self, tags):
        first = await tags.get_or_create("idempotent")
        second = await tags.get_or_create("idempotent")

        assert first.id == second.id

    async def test_positional_and_keyword_arguments_are_forwarded(self, tags):
        positional = await tags.get_or_create("fwd-tag")

        assert (await tags.get_by_name("fwd-tag")).id == positional.id


class TestPerCallFailures:

    async def test_repo_errors_propagate_to_the_caller(self, tags, db_session):
        await tags.create(tag_name="dup")

        with pytest.raises(IntegrityError):
            await tags.create(tag_name="dup")

        await db_session.rollback()

    async def test_commit_is_skipped_when_the_method_raises(
        self, tags, db_session, monkeypatch
    ):
        await tags.create(tag_name="dup-2")
        commits = []
        real_commit = db_session.commit

        async def spy():
            commits.append(1)
            await real_commit()

        monkeypatch.setattr(db_session._session, "commit", spy)

        with pytest.raises(IntegrityError):
            await tags.create(tag_name="dup-2")
        await db_session.rollback()

        assert commits == []


class TestPerCallAttributeAccess:

    async def test_unknown_attribute_raises_attribute_error(self, tags):
        with pytest.raises(AttributeError):
            tags.does_not_exist

    async def test_private_names_are_not_proxied(self, tags):
        with pytest.raises(AttributeError):
            tags._secret

    async def test_non_async_attributes_are_rejected(self, tags):
        # `session` is an instance attribute, not a coroutine function on the class.
        with pytest.raises(AttributeError, match="not an async method"):
            tags.session