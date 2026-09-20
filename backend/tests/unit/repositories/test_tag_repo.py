import pytest

from src.repositories.tag_repo import TagRepository

pytestmark = pytest.mark.db


@pytest.fixture
def tag_repo(db_session):
    return TagRepository(db_session)


class TestTagRepository:

    async def test_get_by_name_found(self, tag_repo, sample_tag):
        found = await tag_repo.get_by_name(sample_tag.tag_name)

        assert found is not None
        assert found.id == sample_tag.id

    async def test_get_by_name_not_found(self, tag_repo):
        found = await tag_repo.get_by_name("nonexistent-tag")

        assert found is None

    async def test_get_or_create_returns_existing(self, tag_repo, sample_tag):
        result = await tag_repo.get_or_create(sample_tag.tag_name)

        assert result.id == sample_tag.id

    async def test_get_or_create_creates_new(self, tag_repo):
        result = await tag_repo.get_or_create("brand-new-tag")

        assert result is not None
        assert result.id is not None
        assert result.tag_name == "brand-new-tag"

    async def test_get_or_create_normalizes_case(self, tag_repo):
        result = await tag_repo.get_or_create("SomeTag")

        assert result.tag_name == "sometag"

    async def test_get_or_create_strips_whitespace(self, tag_repo):
        result = await tag_repo.get_or_create("  spaced-tag  ")

        assert result.tag_name == "spaced-tag"

    async def test_get_or_create_idempotent(self, tag_repo):
        first = await tag_repo.get_or_create("idempotent-tag")
        second = await tag_repo.get_or_create("idempotent-tag")

        assert first.id == second.id