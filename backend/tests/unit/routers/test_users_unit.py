import pytest

from src.api.routers import users
from src.dependencies import get_user_service
from src.schemas.user import UserRead
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.user_service import UserService

pytestmark = pytest.mark.unit

ROUTER = users.router
SERVICE_DEPENDENCY = get_user_service
SERVICE_SPEC = UserService

PASSWORD_PAYLOAD = {"old_password": "OldPassw0rd1", "new_password": "NewPassw0rd1"}


async def test_get_me_returns_current_user_without_service(client, service, actor):
    response = await client.get("/users/me")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == actor.id
    assert body["username"] == actor.username
    assert "password_hash" not in body
    service.get_user_for.assert_not_awaited()


async def test_get_user_returns_user(client, service, actor, fake):
    service.get_user_for.return_value = fake(UserRead, id=5, password_hash="secret")

    response = await client.get("/users/5")

    assert response.status_code == 200
    assert response.json()["id"] == 5
    assert "password_hash" not in response.json()
    service.get_user_for.assert_awaited_once_with(actor, 5)


@pytest.mark.parametrize("error,code", [(ForbiddenError("Forbidden"), 403), (NotFoundError("User not found"), 404)])
async def test_get_user_maps_errors(client, service, error, code):
    service.get_user_for.side_effect = error

    response = await client.get("/users/5")

    assert response.status_code == code
    assert response.json()["detail"] == str(error)


async def test_get_user_invalid_id_returns_422(client, service):
    response = await client.get("/users/abc")

    assert response.status_code == 422
    service.get_user_for.assert_not_awaited()


async def test_update_user_passes_all_fields(client, service, actor, fake):
    service.update_user.return_value = fake(UserRead, id=1, username="renamed")

    response = await client.patch(
        "/users/1", json={"username": "renamed", "email": "renamed@example.com"}
    )

    assert response.status_code == 200
    service.update_user.assert_awaited_once_with(actor, 1, "renamed", "renamed@example.com")


async def test_update_user_passes_partial_fields(client, service, actor, fake):
    service.update_user.return_value = fake(UserRead, id=1)

    response = await client.patch("/users/1", json={"username": "renamed"})

    assert response.status_code == 200
    service.update_user.assert_awaited_once_with(actor, 1, "renamed", None)


@pytest.mark.parametrize(
    "error,code",
    [
        (ForbiddenError("Forbidden"), 403),
        (NotFoundError("User not found"), 404),
        (ConflictError("Username taken"), 409),
        (ValueError("bad"), 400),
    ],
)
async def test_update_user_maps_errors(client, service, error, code):
    service.update_user.side_effect = error

    response = await client.patch("/users/1", json={"username": "x"})

    assert response.status_code == code
    assert response.json()["detail"] == str(error)


async def test_update_user_rejects_invalid_email(client, service):
    response = await client.patch("/users/1", json={"email": "not-an-email"})

    assert response.status_code == 422
    service.update_user.assert_not_awaited()


async def test_change_password_returns_204_for_own_account(client, service, actor):
    response = await client.post(f"/users/{actor.id}/change-password", json=PASSWORD_PAYLOAD)

    assert response.status_code == 204
    assert response.content == b""
    service.change_password.assert_awaited_once_with(actor.id, "OldPassw0rd1", "NewPassw0rd1")


async def test_change_password_for_someone_else_is_forbidden(client, service, actor):
    response = await client.post(f"/users/{actor.id + 1}/change-password", json=PASSWORD_PAYLOAD)

    assert response.status_code == 403
    service.change_password.assert_not_awaited()


async def test_change_password_forbidden_even_for_admin(client, service, as_admin):
    response = await client.post(f"/users/{as_admin.id + 1}/change-password", json=PASSWORD_PAYLOAD)

    assert response.status_code == 403
    service.change_password.assert_not_awaited()


async def test_change_password_value_error_returns_400(client, service, actor):
    service.change_password.side_effect = ValueError("Incorrect current password")

    response = await client.post(f"/users/{actor.id}/change-password", json=PASSWORD_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Incorrect current password"


@pytest.mark.parametrize("payload", [{}, {"old_password": "x"}, {"new_password": "x"}])
async def test_change_password_rejects_invalid_payload(client, service, actor, payload):
    response = await client.post(f"/users/{actor.id}/change-password", json=payload)

    assert response.status_code == 422
    service.change_password.assert_not_awaited()


async def test_delete_user_returns_204(client, service, actor):
    response = await client.delete("/users/1")

    assert response.status_code == 204
    assert response.content == b""
    service.delete_user.assert_awaited_once_with(actor, 1)


@pytest.mark.parametrize("error,code", [(ForbiddenError("Forbidden"), 403), (NotFoundError("User not found"), 404)])
async def test_delete_user_maps_errors(client, service, error, code):
    service.delete_user.side_effect = error

    response = await client.delete("/users/1")

    assert response.status_code == code


async def test_delete_user_invalid_id_returns_422(client, service):
    response = await client.delete("/users/abc")

    assert response.status_code == 422
    service.delete_user.assert_not_awaited()