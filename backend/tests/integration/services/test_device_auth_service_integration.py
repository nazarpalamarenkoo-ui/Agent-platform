from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from src.services.device_auth_service import DeviceAuthService
from src.repositories.device_code_repo import DeviceCodeRepository, DeviceStatus
from src.config import settings


@pytest.fixture
def service(db_session):
    return DeviceAuthService(DeviceCodeRepository(db_session))


class TestInitiateFlow:
    async def test_creates_a_real_pending_device_code(self, service, sample_user):
        device_code = await service.initiate_flow(user_id=sample_user.id, scope="read")

        assert device_code.id is not None
        assert device_code.user_id == sample_user.id
        assert device_code.status == DeviceStatus.PENDING
        assert device_code.expires_at > datetime.now(timezone.utc) + timedelta(
            minutes=14
        )


class TestVerifyAndApprove:
    async def test_approves_pending_code_and_issues_valid_jwt(
        self, service, sample_device_code
    ):
        token = await service.verify_and_approve(sample_device_code.device_code)

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        assert payload["sub"] == str(sample_device_code.user_id)
        assert payload["scope"] == sample_device_code.scope

    async def test_code_cannot_be_approved_twice(self, service, sample_device_code):
        await service.verify_and_approve(sample_device_code.device_code)

        with pytest.raises(ValueError, match="Invalid or expired device code"):
            await service.verify_and_approve(sample_device_code.device_code)

    async def test_raises_for_already_approved_code(
        self, service, approved_device_code
    ):
        with pytest.raises(ValueError, match="Invalid or expired device code"):
            await service.verify_and_approve(approved_device_code.device_code)

    async def test_raises_for_unknown_code(self, service):
        with pytest.raises(ValueError, match="Invalid or expired device code"):
            await service.verify_and_approve("does-not-exist")

    async def test_raises_for_expired_code(self, service, db_session, sample_user):
        from src.db.models.device_code import DeviceCode

        expired = DeviceCode(
            device_code="EXPIRED-CODE",
            user_id=sample_user.id,
            status=DeviceStatus.PENDING,
            scope="read",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            interval=5,
        )
        db_session.add(expired)
        await db_session.commit()

        with pytest.raises(ValueError, match="Invalid or expired device code"):
            await service.verify_and_approve("EXPIRED-CODE")