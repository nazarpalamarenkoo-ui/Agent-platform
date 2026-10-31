from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from src.db.models.config_bundles import ConfigBundle
from src.db.models.device_code import DeviceCode
from src.db.models.users import User
from src.repositories.device_code_repo import DeviceCodeRepository

pytestmark = pytest.mark.integration


def future(days=30):
    return datetime.now(timezone.utc) + timedelta(days=days)


def past(minutes=5):
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


@pytest.fixture
def device_repo(db_session):
    return DeviceCodeRepository(db_session)


async def fresh(session, device_id) -> DeviceCode | None:
    result = await session.execute(
        select(DeviceCode)
        .where(DeviceCode.id == device_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


class TestDeviceConstraints:

    async def test_cannot_create_two_devices_with_same_token_hash(
        self, device_repo, db_session, sample_user
    ):
        await device_repo.create(
            user_id=sample_user.id, name="first", token_hash="a" * 64, expires_at=future()
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await device_repo.create(
                user_id=sample_user.id, name="second", token_hash="a" * 64, expires_at=future()
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_name_is_required(self, device_repo, db_session, sample_user):
        with pytest.raises(IntegrityError):
            await device_repo.create(
                user_id=sample_user.id, token_hash="b" * 64, expires_at=future()
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_cannot_create_device_for_nonexistent_user(self, device_repo, db_session):
        with pytest.raises(IntegrityError):
            await device_repo.create(
                user_id=999_999, name="orphan", token_hash="c" * 64, expires_at=future()
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_cannot_create_device_for_nonexistent_bundle(
        self, device_repo, db_session, sample_user
    ):
        with pytest.raises(IntegrityError):
            await device_repo.create(
                user_id=sample_user.id, name="bad-bundle", token_hash="d" * 64,
                expires_at=future(), config_bundle_id=999_999,
            )
            await db_session.commit()

        await db_session.rollback()


class TestDeleteBehaviour:

    async def test_deleting_user_cascades_to_devices(
        self, db_session, sample_user, make_device_code
    ):
        device = await make_device_code()
        device_id = device.id

        await db_session.execute(delete(User).where(User.id == sample_user.id))
        await db_session.commit()

        assert await fresh(db_session, device_id) is None

    async def test_deleting_bundle_sets_device_bundle_to_null(
        self, db_session, sample_config_bundle, make_device_code
    ):
        device = await make_device_code(config_bundle_id=sample_config_bundle.id)
        device_id = device.id

        await db_session.execute(
            delete(ConfigBundle).where(ConfigBundle.id == sample_config_bundle.id)
        )
        await db_session.commit()

        reloaded = await fresh(db_session, device_id)
        assert reloaded is not None
        assert reloaded.config_bundle_id is None


class TestRevokePersistence:

    async def test_revoke_is_persisted(self, device_repo, db_session, sample_device_code):
        device_id = sample_device_code.id

        await device_repo.revoke(sample_device_code)
        await db_session.commit()

        assert (await fresh(db_session, device_id)).revoked_at is not None

    async def test_revoked_device_is_not_active_but_still_listed_when_requested(
        self, device_repo, db_session, sample_device_code, sample_user
    ):
        token_hash = sample_device_code.token_hash

        await device_repo.revoke(sample_device_code)
        await db_session.commit()

        assert await device_repo.get_active_by_token_hash(token_hash) is None
        assert await device_repo.list_for_user(sample_user.id) == []
        assert [
            d.id for d in await device_repo.list_for_user(sample_user.id, active_only=False)
        ] == [sample_device_code.id]


class TestTouchPersistence:

    async def test_touch_is_persisted(self, device_repo, db_session, sample_device_code):
        device_id = sample_device_code.id
        assert sample_device_code.last_used_at is None

        await device_repo.touch(sample_device_code)
        await db_session.commit()

        assert (await fresh(db_session, device_id)).last_used_at is not None


class TestExpiry:

    async def test_expiry_is_evaluated_by_the_database_comparison(
        self, device_repo, make_device_code
    ):
        valid = await make_device_code()
        expired = await make_device_code(expires_at=past(1))

        assert (await device_repo.get_active_by_token_hash(valid.token_hash)).id == valid.id
        assert await device_repo.get_active_by_token_hash(expired.token_hash) is None

    async def test_timestamps_roundtrip_as_timezone_aware(
        self, db_session, sample_device_code
    ):
        reloaded = await fresh(db_session, sample_device_code.id)

        assert reloaded.expires_at.tzinfo is not None
        assert reloaded.created_at.tzinfo is not None