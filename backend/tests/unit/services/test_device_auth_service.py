from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from jose import jwt

from src.services import device_auth_service as device_auth_module
from src.services.device_auth_service import DeviceAuthService, hash_token
from src.services.errors import NotFoundError

SECRET = "test-secret"
INVALID = "Invalid or expired device token"


@pytest.fixture
def device_code_repo():
    return AsyncMock()


@pytest.fixture
def service(device_code_repo):
    return DeviceAuthService(device_code_repo)


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(device_auth_module.settings, "JWT_SECRET_KEY", SECRET)


def make_token(secret=SECRET, **overrides):
    claims = {
        "sub": "7",
        "typ": "device",
        "scope": "read",
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
    }
    claims.update(overrides)
    return jwt.encode(claims, secret, algorithm="HS256")


class TestHashToken:
    def test_is_deterministic_sha256_hex(self):
        assert hash_token("abc") == hash_token("abc")
        assert len(hash_token("abc")) == 64
        int(hash_token("abc"), 16)

    def test_differs_for_different_tokens(self):
        assert hash_token("a") != hash_token("b")


class TestIssueToken:
    async def test_returns_device_and_token(self, service, device_code_repo):
        created = MagicMock()
        device_code_repo.create.return_value = created

        device, token = await service.issue_token(user_id=7, scope="read write")

        assert device is created
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["sub"] == "7"
        assert payload["scope"] == "read write"
        assert payload["typ"] == "device"
        assert payload["jti"]

    async def test_stores_only_hash_of_token(self, service, device_code_repo):
        _, token = await service.issue_token(user_id=7, scope="s")

        device_code_repo.create.assert_awaited_once()
        kwargs = device_code_repo.create.call_args.kwargs
        assert kwargs["token_hash"] == hash_token(token)
        assert kwargs["user_id"] == 7
        assert kwargs["name"] == "device"
        assert kwargs["config_bundle_id"] is None
        assert "scope" not in kwargs
        assert token not in kwargs.values()

    async def test_passes_name_and_bundle_to_repo(self, service, device_code_repo):
        await service.issue_token(user_id=7, scope="s", name="laptop", config_bundle_id=5)

        kwargs = device_code_repo.create.call_args.kwargs
        assert kwargs["name"] == "laptop"
        assert kwargs["config_bundle_id"] == 5

    async def test_token_and_record_expire_in_about_30_days(self, service, device_code_repo):
        _, token = await service.issue_token(user_id=1, scope="s")

        expires_at = device_code_repo.create.call_args.kwargs["expires_at"]
        expected = datetime.now(timezone.utc) + timedelta(days=30)
        assert abs((expires_at - expected).total_seconds()) < 60
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert abs(payload["exp"] - expected.timestamp()) < 60

    async def test_tokens_are_unique_per_call(self, service):
        _, first = await service.issue_token(user_id=1, scope="s")
        _, second = await service.issue_token(user_id=1, scope="s")

        assert first != second


class TestAuthenticate:
    async def test_valid_token_returns_device_and_touches_it(self, service, device_code_repo):
        token = make_token()
        device = SimpleNamespace(user_id=7)
        device_code_repo.get_active_by_token_hash.return_value = device

        result = await service.authenticate(token)

        assert result is device
        device_code_repo.get_active_by_token_hash.assert_awaited_once_with(hash_token(token))
        device_code_repo.touch.assert_awaited_once_with(device)

    async def test_issued_token_can_be_authenticated(self, service, device_code_repo):
        device_code_repo.create.return_value = SimpleNamespace(user_id=7)
        _, token = await service.issue_token(user_id=7, scope="s")
        device_code_repo.get_active_by_token_hash.return_value = SimpleNamespace(user_id=7)

        await service.authenticate(token)

        device_code_repo.get_active_by_token_hash.assert_awaited_once_with(hash_token(token))

    @pytest.mark.parametrize(
        "token",
        [
            "garbage",
            make_token(secret="other-secret"),
            make_token(exp=datetime.now(timezone.utc) - timedelta(seconds=5)),
        ],
        ids=["garbage", "wrong-secret", "expired"],
    )
    async def test_rejects_invalid_jwt_without_db_lookup(self, service, device_code_repo, token):
        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(token)

        device_code_repo.get_active_by_token_hash.assert_not_awaited()

    async def test_rejects_wrong_token_type(self, service, device_code_repo):
        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(make_token(typ="access"))

        device_code_repo.get_active_by_token_hash.assert_not_awaited()

    async def test_rejects_revoked_or_expired_record(self, service, device_code_repo):
        device_code_repo.get_active_by_token_hash.return_value = None

        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(make_token())

        device_code_repo.touch.assert_not_awaited()

    async def test_rejects_when_subject_does_not_match_record(self, service, device_code_repo):
        device_code_repo.get_active_by_token_hash.return_value = SimpleNamespace(user_id=999)

        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(make_token(sub="7"))

        device_code_repo.touch.assert_not_awaited()


class TestListDevices:
    async def test_delegates_with_defaults(self, service, device_code_repo):
        devices = [SimpleNamespace(id=1)]
        device_code_repo.list_for_user.return_value = devices

        result = await service.list_devices(7)

        assert result is devices
        device_code_repo.list_for_user.assert_awaited_once_with(
            7, active_only=True, limit=100, offset=0
        )

    async def test_passes_filters(self, service, device_code_repo):
        await service.list_devices(7, active_only=False, limit=10, offset=20)

        device_code_repo.list_for_user.assert_awaited_once_with(
            7, active_only=False, limit=10, offset=20
        )


class TestRevokeDevice:
    async def test_revokes_owned_device(self, service, device_code_repo):
        device = SimpleNamespace(id=3)
        device_code_repo.get_owned.return_value = device

        result = await service.revoke_device(user_id=7, device_id=3)

        assert result is device
        device_code_repo.get_owned.assert_awaited_once_with(3, 7)
        device_code_repo.revoke.assert_awaited_once_with(device)

    async def test_raises_when_not_found_or_not_owned(self, service, device_code_repo):
        device_code_repo.get_owned.return_value = None

        with pytest.raises(NotFoundError, match="Device not found"):
            await service.revoke_device(user_id=7, device_id=3)

        device_code_repo.revoke.assert_not_awaited()