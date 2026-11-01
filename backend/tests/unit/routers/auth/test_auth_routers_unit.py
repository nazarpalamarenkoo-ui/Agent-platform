from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.auth import auth as auth_module
from src.api.auth import mail, routes
from src.api.auth.schema import PendingSignup
from src.dependencies import get_user_service
from src.services.user_service import UserService

pytestmark = pytest.mark.unit

ROUTER = routes.router
SERVICE_DEPENDENCY = get_user_service
SERVICE_SPEC = UserService

SECRET = "unit-test-secret"
CREDENTIALS = {"email": "alice@example.com", "password": "Str0ngPassw0rd"}
SIGNUP = {**CREDENTIALS, "username": "alice"}


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "JWT_SECRET_KEY", SECRET)


@pytest.fixture
def user_repo(service):
    # attributes set in __init__ are not part of the class spec, so add it explicitly
    service.user_repo = AsyncMock()
    return service.user_repo


@pytest.fixture
def send_confirmation(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(routes, "send_confirmation_email", mock)
    return mock


@pytest.fixture
def send_reset(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(routes, "send_reset_password_email", mock)
    return mock


def pending():
    return PendingSignup(email="alice@example.com", username="alice", password_hash="hash")


class TestLogin:
    async def test_returns_bearer_token_for_valid_credentials(self, client, service):
        service.authenticate_user.return_value = SimpleNamespace(id=5)

        response = await client.post("/auth/login", json=CREDENTIALS)

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert auth_module.decode_token(body["access_token"], "access")["sub"] == "5"
        service.authenticate_user.assert_awaited_once_with("alice@example.com", "Str0ngPassw0rd")

    async def test_wrong_credentials_return_400(self, client, service):
        service.authenticate_user.return_value = None

        response = await client.post("/auth/login", json=CREDENTIALS)

        assert response.status_code == 400
        assert response.json()["detail"] == "Incorrect email or password"

    @pytest.mark.parametrize(
        "payload",
        [{}, {"email": "alice@example.com"}, {"password": "x"}, {**CREDENTIALS, "email": "not-an-email"}],
    )
    async def test_rejects_invalid_payload(self, client, service, payload):
        response = await client.post("/auth/login", json=payload)

        assert response.status_code == 422
        service.authenticate_user.assert_not_awaited()


class TestSignup:
    async def test_sends_confirmation_email_with_pending_signup_token(
        self, client, service, send_confirmation
    ):
        service.prepare_signup.return_value = "hashed-password"

        response = await client.post("/auth/signup", json=SIGNUP)

        assert response.status_code == 200
        assert response.json() == {"detail": "Email has been sent"}
        service.prepare_signup.assert_awaited_once_with("alice", "alice@example.com", "Str0ngPassw0rd")
        token, username, email = send_confirmation.await_args.args
        assert (username, email) == ("alice", "alice@example.com")
        assert mail.read_signup_confirmation_token(token).password_hash == "hashed-password"

    async def test_token_never_contains_the_plain_password(
        self, client, service, send_confirmation
    ):
        service.prepare_signup.return_value = "hashed-password"

        await client.post("/auth/signup", json=SIGNUP)

        token = send_confirmation.await_args.args[0]
        assert "Str0ngPassw0rd" not in str(auth_module.jwt.get_unverified_claims(token))

    async def test_validation_error_returns_400_and_sends_nothing(
        self, client, service, send_confirmation
    ):
        service.prepare_signup.side_effect = ValueError("Username 'alice' already exists")

        response = await client.post("/auth/signup", json=SIGNUP)

        assert response.status_code == 400
        assert response.json()["detail"] == "Username 'alice' already exists"
        send_confirmation.assert_not_awaited()

    async def test_rejects_invalid_payload(self, client, service):
        response = await client.post("/auth/signup", json={"email": "alice@example.com"})

        assert response.status_code == 422
        service.prepare_signup.assert_not_awaited()


class TestSignupConfirmation:
    def token(self):
        return mail.generate_signup_confirmation_token(pending())

    async def test_creates_user_and_returns_access_token(self, client, service, user_repo):
        user_repo.exists_by_email.return_value = False
        service.create_user_from_hash.return_value = SimpleNamespace(id=3)

        response = await client.post("/auth/signup-confirmation", params={"token": self.token()})

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert auth_module.decode_token(body["access_token"], "access")["sub"] == "3"
        service.create_user_from_hash.assert_awaited_once_with(
            username="alice", email="alice@example.com", password_hash="hash"
        )

    async def test_is_idempotent_for_already_confirmed_email(self, client, service, user_repo):
        user_repo.exists_by_email.return_value = True

        response = await client.post("/auth/signup-confirmation", params={"token": self.token()})

        assert response.status_code == 200
        assert response.json() == {"detail": "Email has been already confirmed"}
        service.create_user_from_hash.assert_not_awaited()

    @pytest.mark.parametrize("token", ["garbage", "a.b.c"])
    async def test_invalid_token_returns_400(self, client, service, user_repo, token):
        response = await client.post("/auth/signup-confirmation", params={"token": token})

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid or expired token"
        service.create_user_from_hash.assert_not_awaited()

    async def test_reset_token_is_not_accepted(self, client, service, user_repo):
        token = mail.generate_password_reset_token(SimpleNamespace(id=1, password_hash="h"))

        response = await client.post("/auth/signup-confirmation", params={"token": token})

        assert response.status_code == 400

    async def test_create_error_returns_400(self, client, service, user_repo):
        user_repo.exists_by_email.return_value = False
        service.create_user_from_hash.side_effect = ValueError("Username 'alice' already exists")

        response = await client.post("/auth/signup-confirmation", params={"token": self.token()})

        assert response.status_code == 400
        assert response.json()["detail"] == "Username 'alice' already exists"

    async def test_requires_token(self, client, service):
        response = await client.post("/auth/signup-confirmation")

        assert response.status_code == 422


class TestPasswordRecovery:
    async def test_sends_reset_email_for_known_user(self, client, service, user_repo, send_reset):
        user_repo.get_by_email.return_value = SimpleNamespace(
            id=5, username="alice", email="alice@example.com", password_hash="h"
        )

        response = await client.post("/auth/password-recovery", params={"email": "alice@example.com"})

        assert response.status_code == 200
        assert response.json() == {"detail": "Email has been sent"}
        token, username, email = send_reset.await_args.args
        assert (username, email) == ("alice", "alice@example.com")
        assert mail.read_password_reset_token(token)[0] == 5

    async def test_unknown_email_gets_identical_response_and_no_email(
        self, client, service, user_repo, send_reset
    ):
        user_repo.get_by_email.return_value = None

        response = await client.post("/auth/password-recovery", params={"email": "ghost@example.com"})

        assert response.status_code == 200
        assert response.json() == {"detail": "Email has been sent"}
        send_reset.assert_not_awaited()

    async def test_rejects_invalid_email(self, client, service, user_repo):
        response = await client.post("/auth/password-recovery", params={"email": "nope"})

        assert response.status_code == 422
        user_repo.get_by_email.assert_not_awaited()


class TestResetPassword:
    BODY = {"new_password": "NewPassw0rd1"}

    def user(self, password_hash="hash-1"):
        return SimpleNamespace(id=5, password_hash=password_hash)

    def token(self, user=None):
        return mail.generate_password_reset_token(user or self.user())

    async def test_updates_password_for_valid_token(self, client, service):
        service.get_user.return_value = self.user()

        response = await client.patch(
            "/auth/reset-password", json={"token": self.token(), **self.BODY}
        )

        assert response.status_code == 200
        assert response.json() == {"detail": "Password updated successfully"}
        service.reset_password.assert_awaited_once_with(5, "NewPassw0rd1")

    async def test_token_is_single_use_after_password_change(self, client, service):
        token = self.token(self.user("hash-1"))
        service.get_user.return_value = self.user("hash-2")

        response = await client.patch("/auth/reset-password", json={"token": token, **self.BODY})

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid or expired token"
        service.reset_password.assert_not_awaited()

    @pytest.mark.parametrize("token", ["garbage", "a.b.c"])
    async def test_invalid_token_returns_400(self, client, service, token):
        response = await client.patch("/auth/reset-password", json={"token": token, **self.BODY})

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid or expired token"
        service.get_user.assert_not_awaited()

    async def test_signup_token_is_not_accepted(self, client, service):
        token = mail.generate_signup_confirmation_token(pending())

        response = await client.patch("/auth/reset-password", json={"token": token, **self.BODY})

        assert response.status_code == 400
        service.reset_password.assert_not_awaited()

    async def test_deleted_user_returns_the_same_generic_400(self, client, service):
        service.get_user.side_effect = ValueError("User 5 not found")

        response = await client.patch(
            "/auth/reset-password", json={"token": self.token(), **self.BODY}
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid or expired token"

    async def test_weak_password_returns_validation_message(self, client, service):
        service.get_user.return_value = self.user()
        service.reset_password.side_effect = ValueError("Password must contain at least one digit")

        response = await client.patch(
            "/auth/reset-password", json={"token": self.token(), "new_password": "NoDigitsHere"}
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Password must contain at least one digit"

    @pytest.mark.parametrize("payload", [{}, {"token": "x"}, {"new_password": "x"}])
    async def test_rejects_invalid_payload(self, client, service, payload):
        response = await client.patch("/auth/reset-password", json=payload)

        assert response.status_code == 422