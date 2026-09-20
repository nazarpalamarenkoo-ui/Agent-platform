from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from jose import jwt

from src.services import device_auth_service as device_auth_module
from src.services.device_auth_service import DeviceAuthService
from src.repositories.device_code_repo import DeviceStatus


@pytest.fixture
def device_code_repo():
    return AsyncMock()


@pytest.fixture
def service(device_code_repo):
    return DeviceAuthService(device_code_repo)


class TestInitiateFlow:
    async def test_creates_device_code_with_expected_fields(
        self, service, device_code_repo, monkeypatch
    ):
        monkeypatch.setattr(
            device_auth_module.secrets, "token_urlsafe", lambda n: "fixed-code"
        )
        created = MagicMock()
        device_code_repo.create.return_value = created

        result = await service.initiate_flow(user_id=7, scope="read write")

        assert result is created
        device_code_repo.create.assert_awaited_once()
        _, kwargs = device_code_repo.create.call_args
        assert kwargs["device_code"] == "fixed-code"
        assert kwargs["user_id"] == 7
        assert kwargs["scope"] == "read write"
        assert kwargs["interval"] == 5
        assert kwargs["status"] == DeviceStatus.PENDING
        assert kwargs["expires_at"] > datetime.now(timezone.utc) + timedelta(
            minutes=14
        )


class TestVerifyAndApprove:
    async def test_returns_valid_jwt_for_valid_code(
        self, service, device_code_repo, monkeypatch
    ):
        monkeypatch.setattr(
            device_auth_module.settings, "JWT_SECRET_KEY", "test-secret"
        )
        device_code = MagicMock(user_id=123, scope="read write")
        device_code_repo.get_valid_by_code.return_value = device_code

        token = await service.verify_and_approve("some-code")

        device_code_repo.get_valid_by_code.assert_awaited_once_with("some-code")
        device_code_repo.approve.assert_awaited_once_with(device_code)

        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert payload["sub"] == "123"
        assert payload["scope"] == "read write"

    async def test_raises_for_invalid_or_expired_code(
        self, service, device_code_repo
    ):
        device_code_repo.get_valid_by_code.return_value = None

        with pytest.raises(ValueError, match="Invalid or expired device code"):
            await service.verify_and_approve("bad-code")

        device_code_repo.approve.assert_not_awaited()