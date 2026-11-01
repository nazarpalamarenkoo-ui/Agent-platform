import pytest
import pytest_asyncio

from src.api.auth import auth as main_auth
from src.api.auth.admin import auth as admin_auth
from src.api.routers import users
from src.db.db_connection import get_db
from src.db.enums.user_role import UserRole
from src.db.models.users import User
from src.repositories.token_usage_event_repo import TokenUsageEventRepository
from src.repositories.user_repo import UserRepository
from src.services.user_service import UserService

pytestmark = [pytest.mark.integration, pytest.mark.db]

OLD_PASSWORD = "OldPassw0rd1"
NEW_PASSWORD = "NewPassw0rd1"


@pytest.fixture
def app(db_session, build_app):
    application = build_app(users.router)
    application.dependency_overrides[get_db] = lambda: db_session
    return application


@pytest.fixture
def login(app):
    def _login(user):
        for dependency in (main_auth.get_current_user, admin_auth.get_current_user):
            app.dependency_overrides[dependency] = lambda: user
        return user

    return _login


@pytest.fixture
def me(sample_user, login):
    return login(sample_user)


@pytest_asyncio.fixture
async def admin_user(make_user, login):
    return login(await make_user(role=UserRole.ADMIN))


@pytest.fixture
def user_service(db_session):
    return UserService(
        user_repo=UserRepository(db_session),
        token_repo=TokenUsageEventRepository(db_session),
    )


@pytest_asyncio.fixture
async def user_with_password(user_service, login):
    """A user with a real bcrypt hash, logged in as the actor."""
    password_hash = await user_service.prepare_signup("pwuser", "pwuser@example.com", OLD_PASSWORD)
    user = await user_service.create_user_from_hash(
        username="pwuser", email="pwuser@example.com", password_hash=password_hash
    )
    return login(user)


# --- authentication ---


@pytest.mark.parametrize(
    "method, url",
    [
        ("GET", "/users/me"),
        ("GET", "/users/1"),
        ("PATCH", "/users/1"),
        ("POST", "/users/1/change-password"),
        ("DELETE", "/users/1"),
    ],
)
async def test_endpoints_require_authentication(client, method, url):
    response = await client.request(method, url)

    assert response.status_code == 401, response.text


# --- me ---


async def test_get_me_returns_current_user_without_secrets(client, me):
    response = await client.get("/users/me")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == me.id
    assert body["username"] == me.username
    assert body["email"] == me.email
    assert body["role"] == UserRole(me.role).value
    assert {"tokens_used", "token_limit"} <= body.keys()
    assert "password_hash" not in body
    assert "password" not in body


# --- get ---


async def test_get_own_user_returns_user(client, me):
    response = await client.get(f"/users/{me.id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == me.id


async def test_regular_user_cannot_get_another_user(client, me, another_user):
    response = await client.get(f"/users/{another_user.id}")

    assert response.status_code == 403, response.text
    assert another_user.email not in response.text


async def test_admin_can_get_another_user(client, admin_user, sample_user):
    response = await client.get(f"/users/{sample_user.id}")

    assert response.status_code == 200, response.text
    assert response.json()["email"] == sample_user.email


async def test_admin_get_unknown_user_returns_404(client, admin_user):
    response = await client.get("/users/999999")

    assert response.status_code == 404, response.text


# --- update ---


async def test_update_user_changes_username(client, me):
    response = await client.patch(f"/users/{me.id}", json={"username": "renamed"})

    assert response.status_code == 200, response.text
    assert response.json()["username"] == "renamed"
    assert (await client.get("/users/me")).json()["username"] == "renamed"


async def test_update_user_changes_email(client, me):
    response = await client.patch(f"/users/{me.id}", json={"email": "renamed@example.com"})

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "renamed@example.com"


async def test_update_user_with_own_username_is_allowed(client, me):
    response = await client.patch(f"/users/{me.id}", json={"username": me.username})

    assert response.status_code == 200, response.text
    assert response.json()["username"] == me.username


async def test_update_user_with_empty_body_changes_nothing(client, me):
    response = await client.patch(f"/users/{me.id}", json={})

    assert response.status_code == 200, response.text
    assert response.json()["username"] == me.username
    assert response.json()["email"] == me.email


async def test_update_user_username_taken_returns_conflict(client, me, another_user):
    response = await client.patch(f"/users/{me.id}", json={"username": another_user.username})

    assert response.status_code in (400, 409), response.text
    assert "already" in response.json()["detail"]


async def test_update_user_email_taken_returns_conflict(client, me, another_user):
    response = await client.patch(f"/users/{me.id}", json={"email": another_user.email})

    assert response.status_code in (400, 409), response.text
    assert "already" in response.json()["detail"]


async def test_update_user_invalid_email_returns_422(client, me):
    response = await client.patch(f"/users/{me.id}", json={"email": "not-an-email"})

    assert response.status_code == 422, response.text


async def test_regular_user_cannot_update_another_user(client, me, another_user, db_session):
    response = await client.patch(f"/users/{another_user.id}", json={"username": "hijacked"})

    assert response.status_code == 403, response.text
    await db_session.refresh(another_user)
    assert another_user.username != "hijacked"


async def test_admin_update_unknown_user_returns_404(client, admin_user):
    response = await client.patch("/users/999999", json={"username": "ghost"})

    assert response.status_code == 404, response.text


# --- change password ---


async def test_change_password_updates_credentials(client, user_with_password, user_service):
    response = await client.post(
        f"/users/{user_with_password.id}/change-password",
        json={"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 204, response.text
    assert await user_service.authenticate_user("pwuser@example.com", NEW_PASSWORD) is not None
    assert await user_service.authenticate_user("pwuser@example.com", OLD_PASSWORD) is None


async def test_change_password_wrong_current_password_returns_400(client, user_with_password, user_service):
    response = await client.post(
        f"/users/{user_with_password.id}/change-password",
        json={"old_password": "WrongPassw0rd1", "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 400, response.text
    assert await user_service.authenticate_user("pwuser@example.com", OLD_PASSWORD) is not None


@pytest.mark.parametrize(
    "new_password, expected",
    [("alllowercase1", "uppercase"), ("ALLUPPERCASE1", "lowercase"), ("NoDigitsHere", "digit")],
)
async def test_change_password_weak_new_password_returns_400(
    client, user_with_password, user_service, new_password, expected
):
    response = await client.post(
        f"/users/{user_with_password.id}/change-password",
        json={"old_password": OLD_PASSWORD, "new_password": new_password},
    )

    assert response.status_code == 400, response.text
    assert expected in response.json()["detail"]
    assert await user_service.authenticate_user("pwuser@example.com", OLD_PASSWORD) is not None


async def test_change_password_of_another_user_returns_403(client, me, another_user):
    response = await client.post(
        f"/users/{another_user.id}/change-password",
        json={"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 403, response.text


async def test_admin_cannot_change_password_of_another_user(client, admin_user, sample_user):
    response = await client.post(
        f"/users/{sample_user.id}/change-password",
        json={"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 403, response.text


@pytest.mark.parametrize("body", [{}, {"old_password": OLD_PASSWORD}, {"new_password": NEW_PASSWORD}])
async def test_change_password_missing_fields_returns_422(client, me, body):
    response = await client.post(f"/users/{me.id}/change-password", json=body)

    assert response.status_code == 422, response.text


# --- delete ---


async def test_regular_user_cannot_delete_another_user(client, me, another_user, db_session):
    response = await client.delete(f"/users/{another_user.id}")

    assert response.status_code == 403, response.text
    assert await db_session.get(User, another_user.id) is not None


async def test_admin_deletes_user(client, admin_user, sample_user):
    response = await client.delete(f"/users/{sample_user.id}")

    assert response.status_code == 204, response.text
    assert (await client.get(f"/users/{sample_user.id}")).status_code == 404


async def test_admin_delete_unknown_user_returns_404(client, admin_user):
    response = await client.delete("/users/999999")

    assert response.status_code == 404, response.text