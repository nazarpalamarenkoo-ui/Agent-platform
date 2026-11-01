from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi_mail import MessageType
from jose import jwt

from src.api.auth import auth as auth_module
from src.api.auth import mail
from src.api.auth.schema import PendingSignup

pytestmark = pytest.mark.unit

SECRET = "unit-test-secret"
INVALID = "Invalid or expired token"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "JWT_SECRET_KEY", SECRET)


def make_user(user_id=5, password_hash="hash-1"):
    return SimpleNamespace(id=user_id, password_hash=password_hash)


def pending():
    return PendingSignup(email="alice@example.com", username="alice", password_hash="hash")


class TestPasswordFingerprint:
    def test_is_deterministic_short_hex(self):
        fp = mail.password_fingerprint("hash")

        assert fp == mail.password_fingerprint("hash")
        assert len(fp) == 16
        int(fp, 16)

    def test_differs_for_different_hashes(self):
        assert mail.password_fingerprint("a") != mail.password_fingerprint("b")

    def test_does_not_contain_the_hash(self):
        assert "secret-hash" not in mail.password_fingerprint("secret-hash")


class TestPasswordResetToken:
    def test_round_trip_returns_user_id_and_fingerprint(self):
        user = make_user(5, "hash-1")

        token = mail.generate_password_reset_token(user)

        assert mail.read_password_reset_token(token) == (5, mail.password_fingerprint("hash-1"))

    def test_token_lives_about_14_hours(self):
        token = mail.generate_password_reset_token(make_user())

        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        expected = datetime.now(timezone.utc) + mail.TOKEN_TTL
        assert abs(payload["exp"] - expected.timestamp()) < 30
        assert mail.TOKEN_TTL == timedelta(hours=14)

    def test_fingerprint_changes_after_password_change(self):
        before = mail.read_password_reset_token(mail.generate_password_reset_token(make_user(5, "old")))
        after = mail.read_password_reset_token(mail.generate_password_reset_token(make_user(5, "new")))

        assert before[1] != after[1]

    @pytest.mark.parametrize(
        "token_factory",
        [
            lambda: "garbage",
            lambda: mail.generate_signup_confirmation_token(pending()),
            lambda: auth_module.create_access_token(5),
            lambda: auth_module.create_token("5", "password_reset", timedelta(hours=1)),
            lambda: auth_module.create_token("abc", "password_reset", timedelta(hours=1), {"fp": "x"}),
            lambda: auth_module.create_token("5", "password_reset", timedelta(seconds=-5), {"fp": "x"}),
        ],
        ids=["garbage", "signup-token", "access-token", "no-fp", "bad-sub", "expired"],
    )
    def test_rejects_invalid_tokens(self, token_factory):
        with pytest.raises(ValueError, match=INVALID):
            mail.read_password_reset_token(token_factory())


class TestSignupConfirmationToken:
    def test_round_trip_restores_pending_signup(self):
        token = mail.generate_signup_confirmation_token(pending())

        assert mail.read_signup_confirmation_token(token) == pending()

    @pytest.mark.parametrize(
        "token_factory",
        [
            lambda: "garbage",
            lambda: mail.generate_password_reset_token(make_user()),
            lambda: auth_module.create_token("alice@example.com", "signup", timedelta(hours=1)),
            lambda: auth_module.create_token(
                "not-an-email", "signup", timedelta(hours=1),
                {"username": "a", "password_hash": "h"},
            ),
            lambda: auth_module.create_token(
                "alice@example.com", "signup", timedelta(seconds=-5),
                {"username": "a", "password_hash": "h"},
            ),
        ],
        ids=["garbage", "reset-token", "missing-claims", "bad-email", "expired"],
    )
    def test_rejects_invalid_tokens(self, token_factory):
        with pytest.raises(ValueError, match=INVALID):
            mail.read_signup_confirmation_token(token_factory())


class TestSendEmails:
    @pytest.fixture
    def fm(self, monkeypatch):
        mock = AsyncMock()
        monkeypatch.setattr(mail, "fm", mock)
        return mock

    async def test_confirmation_email(self, fm):
        await mail.send_confirmation_email("tok", "alice", "alice@example.com")

        fm.send_message.assert_awaited_once()
        message = fm.send_message.await_args.args[0]
        assert fm.send_message.await_args.kwargs == {"template_name": "signup_confirmation.html"}
        assert message.recipients[0].email == "alice@example.com"
        assert "alice" in message.subject
        assert message.subtype == MessageType.html
        assert message.template_body == {
            "project_name": mail.settings.PROJECT_NAME,
            "username": "alice",
            "valid_hours": mail.VALID_HOURS,
            "link": f"{mail.settings.FRONTEND_URL}/confirm-email/tok",
        }

    async def test_reset_password_email(self, fm):
        await mail.send_reset_password_email("tok", "alice", "alice@example.com")

        message = fm.send_message.await_args.args[0]
        assert fm.send_message.await_args.kwargs == {"template_name": "reset_password.html"}
        assert message.recipients[0].email == "alice@example.com"
        assert "alice" in message.subject
        assert message.template_body["link"] == f"{mail.settings.FRONTEND_URL}/reset-password/tok"