from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from src.config import settings
from src.repositories.device_code_repo import DeviceCodeRepository
from src.services.device_auth_service import (
    ALGORITHM,
    DEVICE_TOKEN_TTL,
    TOKEN_TYPE_DEVICE,
    DeviceAuthService,
    hash_token,
)
from src.services.errors import NotFoundError

INVALID = "Invalid or expired device token"


@pytest.fixture
def service(db_session):
    return DeviceAuthService(DeviceCodeRepository(db_session))


def test_hash_token_is_deterministic_sha256():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")
    assert len(hash_token("abc")) == 64


class TestIssueToken:
    async def test_persists_device_and_returns_valid_jwt(self, service, sample_user):
        device, token = await service.issue_token(sample_user.id, "read")

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == str(sample_user.id)
        assert payload["typ"] == TOKEN_TYPE_DEVICE
        assert payload["scope"] == "read"
        assert device.id is not None
        assert device.user_id == sample_user.id
        assert device.name == "device"
        assert device.config_bundle_id is None
        assert device.token_hash == hash_token(token)

    async def test_stores_name_and_bundle_binding(
        self, service, sample_user, sample_config_bundle
    ):
        device, _ = await service.issue_token(
            sample_user.id,
            "read",
            name="my-laptop",
            config_bundle_id=sample_config_bundle.id,
        )

        assert device.name == "my-laptop"
        assert device.config_bundle_id == sample_config_bundle.id

    async def test_token_is_not_stored_in_plain_text(self, service, sample_user):
        device, token = await service.issue_token(sample_user.id, "read")
        assert device.token_hash != token

    async def test_expires_in_about_thirty_days(self, service, sample_user):
        device, _ = await service.issue_token(sample_user.id, "read")

        remaining = device.expires_at - datetime.now(timezone.utc)
        assert DEVICE_TOKEN_TTL - timedelta(minutes=1) < remaining <= DEVICE_TOKEN_TTL

    async def test_each_token_is_unique(self, service, sample_user):
        _, first = await service.issue_token(sample_user.id, "read")
        _, second = await service.issue_token(sample_user.id, "read")
        assert first != second


class TestAuthenticate:
    async def test_returns_device_for_valid_token(self, service, sample_user):
        device, token = await service.issue_token(sample_user.id, "read")

        result = await service.authenticate(token)

        assert result.id == device.id

    async def test_touches_device_on_success(self, service, sample_user):
        _, token = await service.issue_token(sample_user.id, "read")

        result = await service.authenticate(token)

        assert result.last_used_at is not None

    async def test_rejects_garbage(self, service):
        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate("not-a-jwt")

    async def test_rejects_token_signed_with_other_key(self, service, sample_user):
        forged = jwt.encode(
            {"sub": str(sample_user.id), "typ": TOKEN_TYPE_DEVICE,
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            "another-secret", algorithm=ALGORITHM,
        )
        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(forged)

    async def test_rejects_expired_jwt(self, service, sample_user):
        expired = jwt.encode(
            {"sub": str(sample_user.id), "typ": TOKEN_TYPE_DEVICE,
             "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            settings.JWT_SECRET_KEY, algorithm=ALGORITHM,
        )
        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(expired)

    async def test_rejects_wrong_token_type(self, service, sample_user):
        access = jwt.encode(
            {"sub": str(sample_user.id), "typ": "access",
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            settings.JWT_SECRET_KEY, algorithm=ALGORITHM,
        )
        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(access)

    async def test_rejects_valid_jwt_not_registered_in_db(self, service, sample_user):
        unregistered = jwt.encode(
            {"sub": str(sample_user.id), "typ": TOKEN_TYPE_DEVICE,
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            settings.JWT_SECRET_KEY, algorithm=ALGORITHM,
        )
        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(unregistered)

    async def test_rejects_revoked_token(self, service, sample_user):
        device, token = await service.issue_token(sample_user.id, "read")
        await service.revoke_device(sample_user.id, device.id)

        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(token)

    async def test_rejects_token_whose_subject_differs_from_device_owner(
        self, service, db_session, sample_user, another_user
    ):
        forged = jwt.encode(
            {"sub": str(another_user.id), "typ": TOKEN_TYPE_DEVICE,
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            settings.JWT_SECRET_KEY, algorithm=ALGORITHM,
        )
        # the hash is registered under sample_user, but the JWT claims another_user
        await DeviceCodeRepository(db_session).create(
            token_hash=hash_token(forged),
            user_id=sample_user.id,
            name="forged-device",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )

        with pytest.raises(ValueError, match=INVALID):
            await service.authenticate(forged)


class TestListDevices:
    async def test_lists_only_own_devices(self, service, sample_user, another_user):
        mine, _ = await service.issue_token(sample_user.id, "read")
        theirs, _ = await service.issue_token(another_user.id, "read")

        ids = {d.id for d in await service.list_devices(sample_user.id)}

        assert mine.id in ids
        assert theirs.id not in ids

    async def test_active_only_hides_revoked(self, service, sample_user):
        device, _ = await service.issue_token(sample_user.id, "read")
        await service.revoke_device(sample_user.id, device.id)

        active = {d.id for d in await service.list_devices(sample_user.id)}
        everything = {
            d.id for d in await service.list_devices(sample_user.id, active_only=False)
        }

        assert device.id not in active
        assert device.id in everything

    async def test_respects_limit_and_offset(self, service, sample_user):
        for _ in range(3):
            await service.issue_token(sample_user.id, "read")

        first = await service.list_devices(sample_user.id, limit=2, offset=0)
        rest = await service.list_devices(sample_user.id, limit=2, offset=2)

        assert len(first) == 2
        assert len(rest) == 1


class TestRevokeDevice:
    async def test_revokes_own_device(self, service, sample_user):
        device, _ = await service.issue_token(sample_user.id, "read")

        revoked = await service.revoke_device(sample_user.id, device.id)

        assert revoked.id == device.id
        assert revoked.revoked_at is not None

    async def test_cannot_revoke_foreign_device(self, service, sample_user, another_user):
        device, token = await service.issue_token(another_user.id, "read")

        with pytest.raises(NotFoundError, match="Device not found"):
            await service.revoke_device(sample_user.id, device.id)

        assert (await service.authenticate(token)).id == device.id

    async def test_unknown_device(self, service, sample_user):
        with pytest.raises(NotFoundError):
            await service.revoke_device(sample_user.id, 999_999)