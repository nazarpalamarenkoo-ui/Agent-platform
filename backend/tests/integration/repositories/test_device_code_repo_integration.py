import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.repositories.device_code_repo import DeviceCodeRepository
from src.db.models.device_code import DeviceCode
from src.db.enums.device_code_status import DeviceStatus

pytestmark = pytest.mark.integration


@pytest.fixture
def device_repo(db_session):
    return DeviceCodeRepository(db_session)


class TestDeviceCodeUniqueConstraints:

    async def test_cannot_create_two_codes_with_same_device_code_string(
        self, device_repo, db_session, sample_user
    ):
        await device_repo.create(
            device_code="SAME-CODE",
            user_id=sample_user.id,
            status=DeviceStatus.PENDING,
            scope="read",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            interval=5,
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await device_repo.create(
                device_code="SAME-CODE",
                user_id=sample_user.id,
                status=DeviceStatus.PENDING,
                scope="write",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                interval=5,
            )
            await db_session.commit()

        await db_session.rollback()


class TestDeviceCodeForeignKeyIntegrity:

    async def test_cannot_create_code_for_nonexistent_user(
        self, device_repo, db_session
    ):
        with pytest.raises(IntegrityError):
            await device_repo.create(
                device_code="ORPH-0001",
                user_id=999_999,
                status=DeviceStatus.PENDING,
                scope="read",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                interval=5,
            )
            await db_session.commit()

        await db_session.rollback()


class TestApproveRejectPersistence:

    async def test_approve_status_is_persisted(
        self, device_repo, db_session, sample_device_code
    ):
        await device_repo.approve(sample_device_code)
        await db_session.commit()

        code_str = sample_device_code.device_code
        db_session.expire(sample_device_code)
        reloaded = await device_repo.get_by_code(code_str)

        assert reloaded.status == DeviceStatus.APPROVED

    async def test_reject_status_is_persisted(
        self, device_repo, db_session, sample_device_code
    ):
        await device_repo.reject(sample_device_code)
        await db_session.commit()

        code_str = sample_device_code.device_code
        db_session.expire(sample_device_code)
        reloaded = await device_repo.get_by_code(code_str)

        assert reloaded.status == DeviceStatus.REJECTED

    async def test_approved_code_no_longer_appears_as_pending(
        self, device_repo, db_session, sample_device_code, sample_user
    ):
        await device_repo.approve(sample_device_code)
        await db_session.commit()

        pending = await device_repo.get_pending_for_user(sample_user.id)
        ids = {d.id for d in pending}

        assert sample_device_code.id not in ids

    async def test_approved_code_not_returned_by_get_valid(
        self, device_repo, db_session, sample_device_code
    ):
        code_str = sample_device_code.device_code
        await device_repo.approve(sample_device_code)
        await db_session.commit()

        found = await device_repo.get_valid_by_code(code_str)

        assert found is None


class TestExpireStale:

    async def test_expire_stale_is_persisted(
        self, device_repo, db_session, sample_user
    ):
        stale = DeviceCode(
            device_code="STALE-INT-001",
            user_id=sample_user.id,
            status=DeviceStatus.PENDING,
            scope="read",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            interval=5,
        )
        db_session.add(stale)
        await db_session.commit()

        await device_repo.expire_stale()
        await db_session.commit()

        result = await db_session.execute(
            select(DeviceCode)
            .where(DeviceCode.device_code == "STALE-INT-001")
            .execution_options(populate_existing=True)
        )
        reloaded = result.scalar_one()

        assert reloaded.status == DeviceStatus.EXPIRED

    async def test_expire_stale_does_not_affect_already_approved(
        self, device_repo, db_session, sample_user
    ):
        old_approved = DeviceCode(
            device_code="OLD-APPR-001",
            user_id=sample_user.id,
            status=DeviceStatus.APPROVED,
            scope="read",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            interval=5,
        )
        db_session.add(old_approved)
        await db_session.commit()

        await device_repo.expire_stale()
        await db_session.commit()

        result = await db_session.execute(
            select(DeviceCode)
            .where(DeviceCode.device_code == "OLD-APPR-001")
            .execution_options(populate_existing=True)
        )
        reloaded = result.scalar_one()

        assert reloaded.status == DeviceStatus.APPROVED