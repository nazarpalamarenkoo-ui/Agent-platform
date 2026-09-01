import pytest
from sqlalchemy.exc import IntegrityError

from src.repositories.tag_repo import TagRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def tag_repo(db_session):
    return TagRepository(db_session)


class TestTagUniqueConstraints:

    async def test_cannot_create_two_tags_with_same_name(
        self, tag_repo, db_session
    ):
        await tag_repo.create(tag_name="unique-tag")
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await tag_repo.create(tag_name="unique-tag")
            await db_session.commit()

        await db_session.rollback()


class TestGetOrCreatePersistence:

    async def test_get_or_create_new_tag_is_persisted(
        self, tag_repo, db_session
    ):
        tag = await tag_repo.get_or_create("persisted-tag")
        await db_session.commit()

        db_session.expire(tag)
        reloaded = await tag_repo.get_by_name("persisted-tag")

        assert reloaded is not None
        assert reloaded.id == tag.id

    async def test_get_or_create_returns_same_id_across_calls(
        self, tag_repo, db_session
    ):
        first = await tag_repo.get_or_create("stable-tag")
        await db_session.commit()

        second = await tag_repo.get_or_create("stable-tag")
        await db_session.commit()

        assert first.id == second.id

    async def test_get_or_create_normalizes_before_persisting(
        self, tag_repo, db_session
    ):
        tag = await tag_repo.get_or_create("  MixedCase  ")
        await db_session.commit()

        found = await tag_repo.get_by_name("mixedcase")

        assert found is not None
        assert found.id == tag.id

    async def test_get_or_create_does_not_duplicate_after_normalization(
        self, tag_repo, db_session
    ):
        first = await tag_repo.get_or_create("NoDupe")
        await db_session.commit()

        second = await tag_repo.get_or_create("nodupe")
        await db_session.commit()

        assert first.id == second.id