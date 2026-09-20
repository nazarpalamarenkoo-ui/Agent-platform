import pytest

from src.api.routers import users
from src.db.models.users import User
from src.dependencies import get_user_service
from src.repositories.token_usage_event_repo import TokenUsageEventRepository
from src.repositories.user_repo import UserRepository
from src.services.user_service import UserService

pytestmark = [pytest.mark.integration, pytest.mark.db]

USER_PAYLOAD = {
    "username": "newuser",
    "email": "new@example.com",
    "password": "Str0ngPassw0rd",
}


@pytest.fixture
def user_service(db_session):
    return UserService(UserRepository(db_session), TokenUsageEventRepository(db_session))


@pytest.fixture
def app(build_app, user_service):
    application = build_app(users.router)
    application.dependency_overrides[get_user_service] = lambda: user_service
    return application


async def test_create_user_returns_201_without_password_data(client):
    response = await client.post("/users", json=USER_PAYLOAD)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"]
    assert body["username"] == "newuser"
    assert body["email"] == "new@example.com"
    assert "password" not in body
    assert "password_hash" not in body


async def test_create_user_stores_hashed_password(client, db_session):
    response = await client.post("/users", json=USER_PAYLOAD)

    user = await db_session.get(User, response.json()["id"])
    assert user.password_hash != USER_PAYLOAD["password"]
    assert user.password_hash.startswith("$2")


async def test_create_user_duplicate_username_returns_400(client, sample_user):
    payload = {**USER_PAYLOAD, "username": sample_user.username}

    response = await client.post("/users", json=payload)

    assert response.status_code == 400, response.text
    assert "already exists" in response.json()["detail"]


async def test_create_user_duplicate_email_returns_400(client, sample_user):
    payload = {**USER_PAYLOAD, "email": sample_user.email}

    response = await client.post("/users", json=payload)

    assert response.status_code == 400, response.text
    assert "already registered" in response.json()["detail"]


@pytest.mark.parametrize(
    "password, expected",
    [
        ("alllowercase1", "uppercase"),
        ("ALLUPPERCASE1", "lowercase"),
        ("NoDigitsHere", "digit"),
    ],
)
async def test_create_user_weak_password_returns_400(client, password, expected):
    response = await client.post("/users", json={**USER_PAYLOAD, "password": password})

    assert response.status_code == 400, response.text
    assert expected in response.json()["detail"]


async def test_created_user_can_be_fetched(client):
    created = await client.post("/users", json=USER_PAYLOAD)
    assert created.status_code == 201, created.text

    response = await client.get(f"/users/{created.json()['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["username"] == "newuser"


async def test_get_user_returns_existing_user(client, sample_user):
    response = await client.get(f"/users/{sample_user.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == sample_user.id
    assert body["username"] == sample_user.username
    assert body["email"] == sample_user.email
    assert "password_hash" not in body


async def test_get_user_unknown_id_returns_400(client):
    response = await client.get("/users/999999")

    assert response.status_code == 400, response.text
    assert "999999" in response.json()["detail"]


async def test_update_user_changes_username(client, sample_user):
    response = await client.patch(f"/users/{sample_user.id}", json={"username": "renamed"})

    assert response.status_code == 200, response.text
    assert response.json()["username"] == "renamed"


async def test_update_user_changes_email(client, sample_user):
    response = await client.patch(f"/users/{sample_user.id}", json={"email": "renamed@example.com"})

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "renamed@example.com"


async def test_update_user_with_own_username_is_allowed(client, sample_user):
    response = await client.patch(f"/users/{sample_user.id}", json={"username": sample_user.username})

    assert response.status_code == 200, response.text
    assert response.json()["username"] == sample_user.username


async def test_update_user_with_empty_body_changes_nothing(client, sample_user):
    response = await client.patch(f"/users/{sample_user.id}", json={})

    assert response.status_code == 200, response.text
    assert response.json()["username"] == sample_user.username


async def test_update_user_username_taken_returns_400(client, sample_user, another_user):
    response = await client.patch(f"/users/{sample_user.id}", json={"username": another_user.username})

    assert response.status_code == 400, response.text
    assert "already exists" in response.json()["detail"]


async def test_update_user_email_taken_returns_400(client, sample_user, another_user):
    response = await client.patch(f"/users/{sample_user.id}", json={"email": another_user.email})

    assert response.status_code == 400, response.text
    assert "already registered" in response.json()["detail"]


async def test_update_unknown_user_returns_400(client):
    response = await client.patch("/users/999999", json={"username": "ghost"})

    assert response.status_code == 400, response.text


async def test_change_password_updates_credentials(client, user_service):
    await client.post("/users", json={**USER_PAYLOAD, "password": "OldPassw0rd1"})
    created = await user_service.user_repo.get_by_email(USER_PAYLOAD["email"])

    response = await client.post(
        f"/users/{created.id}/change-password",
        json={"old_password": "OldPassw0rd1", "new_password": "NewPassw0rd1"},
    )

    assert response.status_code == 204, response.text
    assert await user_service.authenticate_user(USER_PAYLOAD["email"], "NewPassw0rd1") is not None
    assert await user_service.authenticate_user(USER_PAYLOAD["email"], "OldPassw0rd1") is None


async def test_change_password_wrong_current_password_returns_400(client):
    created = await client.post("/users", json={**USER_PAYLOAD, "password": "OldPassw0rd1"})
    assert created.status_code == 201, created.text

    response = await client.post(
        f"/users/{created.json()['id']}/change-password",
        json={"old_password": "WrongPassw0rd1", "new_password": "NewPassw0rd1"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Incorrect current password"


async def test_change_password_weak_new_password_returns_400(client):
    created = await client.post("/users", json={**USER_PAYLOAD, "password": "OldPassw0rd1"})
    assert created.status_code == 201, created.text

    response = await client.post(
        f"/users/{created.json()['id']}/change-password",
        json={"old_password": "OldPassw0rd1", "new_password": "weakpassword1"},
    )

    assert response.status_code == 400, response.text
    assert "uppercase" in response.json()["detail"]


async def test_change_password_unknown_user_returns_400(client):
    response = await client.post(
        "/users/999999/change-password",
        json={"old_password": "OldPassw0rd1", "new_password": "NewPassw0rd1"},
    )

    assert response.status_code == 400, response.text


async def test_delete_user_returns_204_and_removes_user(client):
    created = await client.post("/users", json=USER_PAYLOAD)
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    response = await client.delete(f"/users/{user_id}")
    fetched = await client.get(f"/users/{user_id}")

    assert response.status_code == 204, response.text
    assert fetched.status_code == 400, fetched.text


async def test_delete_unknown_user_returns_404(client):
    response = await client.delete("/users/999999")

    assert response.status_code == 404, response.text