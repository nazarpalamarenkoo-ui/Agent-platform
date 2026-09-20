import pytest

from src.repositories.base_repo import BaseRepository
from src.db.models.users import User

pytestmark = pytest.mark.db


@pytest.fixture
def user_repo(db_session):
    return BaseRepository(db_session, User)


class TestBaseRepository:

    async def test_create_persists_entity(self, user_repo):
        user = await user_repo.create(
            username="baseuser",
            email="base@example.com",
            password_hash="hashed",
        )

        assert user.id is not None
        assert user.username == "baseuser"

    async def test_get_by_id_returns_entity(self, user_repo, sample_user):
        found = await user_repo.get_by_id(sample_user.id)

        assert found is not None
        assert found.id == sample_user.id
        assert found.username == sample_user.username

    async def test_get_by_id_returns_none_when_missing(self, user_repo):
        found = await user_repo.get_by_id(999999)

        assert found is None

    async def test_get_all_returns_created_entities(self, user_repo, sample_user, another_user):
        results = await user_repo.get_all()

        ids = {u.id for u in results}
        assert sample_user.id in ids
        assert another_user.id in ids

    async def test_get_all_respects_limit_and_offset(self, user_repo, sample_user, another_user):
        results = await user_repo.get_all(limit=1, offset=0)

        assert len(results) == 1

    async def test_update_modifies_fields(self, user_repo, sample_user):
        updated = await user_repo.update(sample_user, username="renamed")

        assert updated.username == "renamed"
        assert updated is sample_user

    async def test_delete_removes_entity(self, user_repo, sample_user):
        await user_repo.delete(sample_user)

        found = await user_repo.get_by_id(sample_user.id)
        assert found is None