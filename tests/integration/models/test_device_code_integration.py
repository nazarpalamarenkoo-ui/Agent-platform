import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.models.device_code import DeviceCode
from src.db.models.users import User
from src.db.enums.device_code_status import DeviceStatus

pytestmark = pytest.mark.integration


class TestDeviceCodeConstraints:

    async def test_duplicate_device_code_raises_integrity_error(
        self, db_session, sample_device_code, sample_user
    ):
        duplicate = DeviceCode(
            device_code=sample_device_code.device_code,
            user_id=sample_user.id,
            status=DeviceStatus.PENDING,
            scope="read",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            interval=5,
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_cannot_create_device_code_with_nonexistent_user_id(self, db_session):
        device_code = DeviceCode(
            device_code="ORPHAN-0001",
            user_id=999_999,
            status=DeviceStatus.PENDING,
            scope="read",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            interval=5,
        )
        db_session.add(device_code)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_status_defaults_to_pending(self, db_session, sample_user):
        device_code = DeviceCode(
            device_code="NODEFAULT-0001",
            user_id=sample_user.id,
            scope="read",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            interval=5,
        )
        db_session.add(device_code)
        await db_session.commit()
        await db_session.refresh(device_code)

        assert device_code.status == DeviceStatus.PENDING


class TestDeviceCodeCascadeDelete:

    async def test_deleting_user_cascades_to_device_codes(
        self, db_session, sample_device_code, approved_device_code, sample_user
    ):
        code_ids = [sample_device_code.id, approved_device_code.id]

        user_to_delete = await db_session.get(User, sample_user.id)
        await db_session.delete(user_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(DeviceCode).where(DeviceCode.id.in_(code_ids))
        )
        assert result.scalars().all() == []


class TestDeviceCodeStatusTransitions:

    async def test_device_code_status_can_be_updated_to_approved(
        self, db_session, sample_device_code
    ):
        device = await db_session.get(DeviceCode, sample_device_code.id)
        device.status = DeviceStatus.APPROVED
        db_session.add(device)
        await db_session.commit()
        await db_session.refresh(device)

        assert device.status == DeviceStatus.APPROVED