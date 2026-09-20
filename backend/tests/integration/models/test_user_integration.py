import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.models.users import User
from src.db.models.config_bundles import ConfigBundle
from src.db.models.token_usage_events import TokenUsageEvent


pytestmark = pytest.mark.integration


class TestUserCreation:

    async def test_create_user_sets_defaults(self, db_session, sample_user):
        assert sample_user.id is not None
        assert sample_user.username == "testuser"
        assert sample_user.email == "test@example.com"
        assert sample_user.token_limit == 100_000
        assert sample_user.tokens_used == 0
        assert sample_user.created_at is not None

    async def test_reload_user_from_db(self, db_session, sample_user):
        result = await db_session.execute(
            select(User).where(User.id == sample_user.id)
        )
        reloaded = result.scalar_one()

        assert reloaded.username == sample_user.username
        assert reloaded.email == sample_user.email


class TestUserUniqueConstraints:

    async def test_duplicate_username_raises_integrity_error(
        self, db_session, sample_user
    ):
        duplicate = User(
            username=sample_user.username,
            email="different-email@example.com",
            password_hash="hashed",
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_duplicate_email_raises_integrity_error(
        self, db_session, sample_user
    ):
        duplicate = User(
            username="different-username",
            email=sample_user.email,
            password_hash="hashed",
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_different_username_and_email_is_allowed(
        self, db_session, sample_user
    ):
        other = User(
            username="fresh-username",
            email="fresh-email@example.com",
            password_hash="hashed",
        )
        db_session.add(other)
        await db_session.commit()
        await db_session.refresh(other)

        assert other.id is not None
        assert other.id != sample_user.id


class TestUserCascadeDelete:

    async def test_deleting_user_cascades_to_config_bundles(
        self, db_session, sample_user, sample_agent_profile
    ):
        bundle_1 = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="bundle-one",
            description="First bundle",
        )
        bundle_2 = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="bundle-two",
            description="Second bundle",
        )
        db_session.add_all([bundle_1, bundle_2])
        await db_session.commit()

        bundle_ids = [bundle_1.id, bundle_2.id]

        result = await db_session.execute(
            select(ConfigBundle).where(ConfigBundle.id.in_(bundle_ids))
        )
        assert len(result.scalars().all()) == 2

        user_to_delete = await db_session.get(User, sample_user.id)
        await db_session.delete(user_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(ConfigBundle).where(ConfigBundle.id.in_(bundle_ids))
        )
        assert result.scalars().all() == []

        deleted_user = await db_session.get(User, sample_user.id)
        assert deleted_user is None

    async def test_deleting_user_cascades_to_token_usage_events(
        self, db_session, sample_user, sample_agent_profile
    ):
        event = TokenUsageEvent(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            tokens_used=250,
        )
        db_session.add(event)
        await db_session.commit()

        event_id = event.id

        user_to_delete = await db_session.get(User, sample_user.id)
        await db_session.delete(user_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(TokenUsageEvent).where(TokenUsageEvent.id == event_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_deleting_user_does_not_affect_other_users(
        self, db_session, sample_user, another_user, sample_agent_profile
    ):
        bundle = ConfigBundle(
            user_id=another_user.id,
            agent_id=sample_agent_profile.id,
            name="untouched-bundle",
            description="Belongs to another_user",
        )
        db_session.add(bundle)
        await db_session.commit()
        bundle_id = bundle.id

        user_to_delete = await db_session.get(User, sample_user.id)
        await db_session.delete(user_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(ConfigBundle).where(ConfigBundle.id == bundle_id)
        )
        assert result.scalar_one_or_none() is not None

        still_there = await db_session.get(User, another_user.id)
        assert still_there is not None