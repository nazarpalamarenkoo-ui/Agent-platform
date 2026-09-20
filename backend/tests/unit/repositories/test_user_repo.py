import pytest

from src.repositories.user_repo import UserRepository

pytestmark = pytest.mark.db


@pytest.fixture
def user_repo(db_session):
    return UserRepository(db_session)


class TestUserRepository:

    async def test_get_by_username_found(self, user_repo, sample_user):
        found = await user_repo.get_by_username(sample_user.username)

        assert found is not None
        assert found.id == sample_user.id

    async def test_get_by_username_not_found(self, user_repo):
        found = await user_repo.get_by_username("nonexistent")

        assert found is None

    async def test_get_by_email_found(self, user_repo, sample_user):
        found = await user_repo.get_by_email(sample_user.email)

        assert found is not None
        assert found.id == sample_user.id

    async def test_get_by_email_not_found(self, user_repo):
        found = await user_repo.get_by_email("nobody@example.com")

        assert found is None

    async def test_update_password_changes_hash(self, user_repo, sample_user):
        updated = await user_repo.update_password(sample_user, "new-hash")

        assert updated.password_hash == "new-hash"

    async def test_reset_usage_zeroes_tokens(self, user_repo, sample_user):
        sample_user.tokens_used = 500
        await user_repo.session.flush()

        updated = await user_repo.reset_usage(sample_user)

        assert updated.tokens_used == 0