import pytest

from src.api.routers import users
from src.dependencies import get_user_service
from src.services.user_service import UserService
from src.schemas.user import UserRead

pytestmark = pytest.mark.unit

ROUTER = users.router
SERVICE_DEPENDENCY = get_user_service
SERVICE_SPEC = UserService

CREATE_PAYLOAD = {
    "username": "newuser",
    "email": "new@example.com",
    "password": "Str0ngPassw0rd",
}

PASSWORD_PAYLOAD = {
    "old_password": "OldPassw0rd1",
    "new_password": "NewPassw0rd1",
}


async def test_create_user_returns_201(client, service, fake):
    service.create_user.return_value = fake(UserRead, id=3, username="newuser", email="new@example.com")

    response = await client.post("/users", json=CREATE_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 3
    assert body["username"] == "newuser"
    assert body["email"] == "new@example.com"
    service.create_user.assert_awaited_once_with("newuser", "new@example.com", "Str0ngPassw0rd")


async def test_create_user_response_does_not_leak_password_data(client, service, fake):
    service.create_user.return_value = fake(UserRead, id=3, password_hash="hashed-secret")

    response = await client.post("/users", json=CREATE_PAYLOAD)

    body = response.json()
    assert "password" not in body
    assert "password_hash" not in body


async def test_create_user_value_error_returns_400(client, service):
    service.create_user.side_effect = ValueError("Username 'newuser' already exists")

    response = await client.post("/users", json=CREATE_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Username 'newuser' already exists"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"username": "newuser"},
        {"username": "newuser", "email": "new@example.com"},
        {**CREATE_PAYLOAD, "username": ["x"]},
    ],
)
async def test_create_user_rejects_invalid_payload(client, service, payload):
    response = await client.post("/users", json=payload)

    assert response.status_code == 422
    service.create_user.assert_not_awaited()


async def test_get_user_returns_user(client, service, fake):
    service.get_user.return_value = fake(UserRead, id=5, password_hash="hashed-secret")

    response = await client.get("/users/5")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 5
    assert "password_hash" not in body
    service.get_user.assert_awaited_once_with(5)


async def test_get_user_value_error_returns_400(client, service):
    service.get_user.side_effect = ValueError("User 5 not found")

    response = await client.get("/users/5")

    assert response.status_code == 400
    assert response.json()["detail"] == "User 5 not found"


async def test_get_user_invalid_id_returns_422(client, service):
    response = await client.get("/users/abc")

    assert response.status_code == 422
    service.get_user.assert_not_awaited()


async def test_update_user_passes_all_fields(client, service, fake):
    service.update_user.return_value = fake(UserRead, id=1, username="renamed", email="renamed@example.com")

    response = await client.patch("/users/1", json={"username": "renamed", "email": "renamed@example.com"})

    assert response.status_code == 200
    assert response.json()["username"] == "renamed"
    service.update_user.assert_awaited_once_with(1, "renamed", "renamed@example.com")


async def test_update_user_passes_partial_fields(client, service, fake):
    service.update_user.return_value = fake(UserRead, id=1, username="renamed")

    response = await client.patch("/users/1", json={"username": "renamed"})

    assert response.status_code == 200
    service.update_user.assert_awaited_once_with(1, "renamed", None)


async def test_update_user_value_error_returns_400(client, service):
    service.update_user.side_effect = ValueError("Email 'taken@example.com' already registered")

    response = await client.patch("/users/1", json={"email": "taken@example.com"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Email 'taken@example.com' already registered"


async def test_update_user_invalid_id_returns_422(client, service):
    response = await client.patch("/users/abc", json={"username": "renamed"})

    assert response.status_code == 422
    service.update_user.assert_not_awaited()


async def test_change_password_returns_204(client, service):
    service.change_password.return_value = True

    response = await client.post("/users/1/change-password", json=PASSWORD_PAYLOAD)

    assert response.status_code == 204
    assert response.content == b""
    service.change_password.assert_awaited_once_with(1, "OldPassw0rd1", "NewPassw0rd1")


async def test_change_password_value_error_returns_400(client, service):
    service.change_password.side_effect = ValueError("Incorrect current password")

    response = await client.post("/users/1/change-password", json=PASSWORD_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Incorrect current password"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"old_password": "OldPassw0rd1"},
        {"new_password": "NewPassw0rd1"},
    ],
)
async def test_change_password_rejects_invalid_payload(client, service, payload):
    response = await client.post("/users/1/change-password", json=payload)

    assert response.status_code == 422
    service.change_password.assert_not_awaited()


async def test_delete_user_returns_204(client, service):
    service.delete_user.return_value = None

    response = await client.delete("/users/1")

    assert response.status_code == 204
    assert response.content == b""
    service.delete_user.assert_awaited_once_with(1)


async def test_delete_user_not_found_returns_404(client, service):
    service.delete_user.side_effect = ValueError("User 1 not found")

    response = await client.delete("/users/1")

    assert response.status_code == 404
    assert response.json()["detail"] == "User 1 not found"


async def test_delete_user_invalid_id_returns_422(client, service):
    response = await client.delete("/users/abc")

    assert response.status_code == 422
    service.delete_user.assert_not_awaited()