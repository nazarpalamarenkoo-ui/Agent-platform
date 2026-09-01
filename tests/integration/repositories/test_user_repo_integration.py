import pytest
from sqlalchemy.exc import IntegrityError

from src.repositories.user_repo import UserRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def user_repo(db_session):
    return UserRepository(db_session)


class TestUserUniqueConstraints:

    async def test_cannot_create_two_users_with_same_username(
        self, user_repo, db_session
    ):
        await user_repo.create(
            username="duplicate",
            email="first@example.com",
            password_hash="hashed",
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await user_repo.create(
                username="duplicate",
                email="second@example.com",
                password_hash="hashed",
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_cannot_create_two_users_with_same_email(
        self, user_repo, db_session
    ):
        await user_repo.create(
            username="user_one",
            email="shared@example.com",
            password_hash="hashed",
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await user_repo.create(
                username="user_two",
                email="shared@example.com",
                password_hash="hashed",
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_can_reuse_username_after_user_deleted(
        self, user_repo, db_session
    ):
        user = await user_repo.create(
            username="recyclable",
            email="recycle@example.com",
            password_hash="hashed",
        )
        await db_session.commit()

        await user_repo.delete(user)
        await db_session.commit()

        recreated = await user_repo.create(
            username="recyclable",
            email="new@example.com",
            password_hash="hashed",
        )
        await db_session.commit()
        await db_session.refresh(recreated)

        assert recreated.id is not None


class TestUserUpdatePassword:

    async def test_update_password_is_persisted(
        self, user_repo, db_session, sample_user
    ):
        await user_repo.update_password(sample_user, "new-hash-xyz")
        await db_session.commit()

        user_id = sample_user.id
        db_session.expire(sample_user)
        reloaded = await user_repo.get_by_id(user_id)

        assert reloaded.password_hash == "new-hash-xyz"

    async def test_update_password_does_not_affect_other_fields(
        self, user_repo, db_session, sample_user
    ):
        original_email = sample_user.email

        await user_repo.update_password(sample_user, "another-hash")
        await db_session.commit()

        user_id = sample_user.id
        db_session.expire(sample_user)
        reloaded = await user_repo.get_by_id(user_id)

        assert reloaded.email == original_email


class TestUserResetUsage:

    async def test_reset_usage_is_persisted(
        self, user_repo, db_session, sample_user
    ):
        sample_user.tokens_used = 9999
        await db_session.commit()

        await user_repo.reset_usage(sample_user)
        await db_session.commit()

        user_id = sample_user.id
        db_session.expire(sample_user)
        reloaded = await user_repo.get_by_id(user_id)

        assert reloaded.tokens_used == 0

    async def test_reset_usage_does_not_affect_token_limit(
        self, user_repo, db_session, sample_user
    ):
        sample_user.token_limit = 50_000
        sample_user.tokens_used = 10_000
        await db_session.commit()

        await user_repo.reset_usage(sample_user)
        await db_session.commit()

        user_id = sample_user.id
        db_session.expire(sample_user)
        reloaded = await user_repo.get_by_id(user_id)

        assert reloaded.token_limit == 50_000
        assert reloaded.tokens_used == 0