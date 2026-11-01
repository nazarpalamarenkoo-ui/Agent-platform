from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from jose import JWTError, jwt

from src.api.auth import auth as main_auth
from src.api.auth.admin import auth as admin_auth

pytestmark = pytest.mark.unit

SECRET = "unit-test-secret"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(main_auth.settings, "JWT_SECRET_KEY", SECRET)


@pytest.fixture(params=[main_auth, admin_auth], ids=["auth", "admin_auth"])
def module(request):
    return request.param


def encode(secret=SECRET, **claims):
    claims.setdefault("exp", datetime.now(timezone.utc) + timedelta(minutes=5))
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
def repo(module, monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(module, "UserRepository", lambda session: mock)
    return mock


class TestCreateAndDecodeToken:
    def test_payload_contains_subject_type_and_expiry(self, module):
        token = module.create_token("5", "access", timedelta(minutes=10))

        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["sub"] == "5"
        assert payload["typ"] == "access"
        expected = datetime.now(timezone.utc) + timedelta(minutes=10)
        assert abs(payload["exp"] - expected.timestamp()) < 30

    def test_extra_claims_are_included_but_cannot_override_sub_and_typ(self, module):
        token = module.create_token(
            "5", "access", timedelta(minutes=1), extra={"fp": "abc", "sub": "evil", "typ": "evil"}
        )

        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["fp"] == "abc"
        assert payload["sub"] == "5"
        assert payload["typ"] == "access"

    def test_decode_returns_payload_for_expected_type(self, module):
        token = module.create_token("5", "signup", timedelta(minutes=1))

        assert module.decode_token(token, "signup")["sub"] == "5"

    def test_decode_rejects_unexpected_type(self, module):
        token = module.create_token("5", "password_reset", timedelta(minutes=1))

        with pytest.raises(JWTError):
            module.decode_token(token, "access")

    def test_decode_rejects_expired_token(self, module):
        token = module.create_token("5", "access", timedelta(seconds=-5))

        with pytest.raises(JWTError):
            module.decode_token(token, "access")

    def test_decode_rejects_token_signed_with_other_key(self, module):
        with pytest.raises(JWTError):
            module.decode_token(encode("other", sub="5", typ="access"), "access")

    def test_decode_rejects_garbage(self, module):
        with pytest.raises(JWTError):
            module.decode_token("garbage", "access")


class TestCreateAccessToken:
    def test_is_an_access_token_for_the_user_valid_for_two_hours(self, module):
        token = module.create_access_token(42)

        payload = module.decode_token(token, module.TOKEN_TYPE_ACCESS)
        assert payload["sub"] == "42"
        expected = datetime.now(timezone.utc) + timedelta(minutes=120)
        assert abs(payload["exp"] - expected.timestamp()) < 30


class TestGetCurrentUser:
    async def test_returns_user_for_valid_token(self, module, repo):
        user = SimpleNamespace(id=5)
        repo.get_by_id.return_value = user

        result = await module.get_current_user(
            token=module.create_access_token(5), session=object()
        )

        assert result is user
        repo.get_by_id.assert_awaited_once_with(5)

    @pytest.mark.parametrize(
        "make_token",
        [
            lambda m: "garbage",
            lambda m: encode("other", sub="5", typ="access"),
            lambda m: encode(sub="5", typ="password_reset"),
            lambda m: encode(sub="5", typ="signup"),
            lambda m: encode(sub="not-a-number", typ="access"),
            lambda m: encode(typ="access"),
            lambda m: encode(sub="5", typ="access", exp=datetime.now(timezone.utc) - timedelta(seconds=5)),
        ],
        ids=["garbage", "wrong-key", "reset-token", "signup-token", "bad-sub", "no-sub", "expired"],
    )
    async def test_rejects_invalid_tokens_with_401(self, module, repo, make_token):
        with pytest.raises(HTTPException) as exc:
            await module.get_current_user(token=make_token(module), session=object())

        assert exc.value.status_code == 401
        assert exc.value.headers == {"WWW-Authenticate": "Bearer"}
        repo.get_by_id.assert_not_awaited()

    async def test_rejects_token_of_deleted_user(self, module, repo):
        repo.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc:
            await module.get_current_user(token=module.create_access_token(5), session=object())

        assert exc.value.status_code == 401


class TestRoleGuards:
    async def test_require_admin_allows_admin(self, module):
        user = SimpleNamespace(is_admin=True)
        assert await module.require_admin(user) is user

    async def test_require_admin_rejects_regular_user(self, module):
        with pytest.raises(HTTPException) as exc:
            await module.require_admin(SimpleNamespace(is_admin=False))

        assert exc.value.status_code == 403
        assert exc.value.detail == "Admin access required"

    async def test_require_super_admin_allows_super_admin(self):
        user = SimpleNamespace(is_super_admin=True)
        assert await admin_auth.require_super_admin(user) is user

    async def test_require_super_admin_rejects_plain_admin(self):
        with pytest.raises(HTTPException) as exc:
            await admin_auth.require_super_admin(
                SimpleNamespace(is_admin=True, is_super_admin=False)
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == "Super admin access required"