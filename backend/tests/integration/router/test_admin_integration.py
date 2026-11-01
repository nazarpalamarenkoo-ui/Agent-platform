import pytest
import pytest_asyncio

from src.api.auth import auth as main_auth
from src.api.auth.admin import auth as admin_auth
from src.api.routers import admin
from src.db.db_connection import get_db
from src.db.enums.user_role import UserRole

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    application = build_app(admin.router)
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


@pytest_asyncio.fixture
async def super_admin(make_user, login):
    return login(await make_user(role=UserRole.SUPER_ADMIN))


ROLE_BODY = {"role": UserRole.USER.value}
TOKEN_LIMIT_BODY = {"token_limit": 1000}

SUPER_ADMIN_ONLY = [
    ("GET", "/admin/admins", None),
    ("PUT", "/admin/users/1/role", ROLE_BODY),
]
ADMIN_ONLY = [
    ("GET", "/admin/users", None),
    ("GET", "/admin/users/1", None),
    ("PUT", "/admin/users/1/token-limit", TOKEN_LIMIT_BODY),
    ("POST", "/admin/users/1/reset-usage", None),
]


# --- access control ---


@pytest.mark.parametrize("method, url, body", SUPER_ADMIN_ONLY + ADMIN_ONLY)
async def test_endpoints_require_authentication(client, method, url, body):
    response = await client.request(method, url, json=body)

    assert response.status_code == 401, response.text


@pytest.mark.parametrize("method, url, body", SUPER_ADMIN_ONLY + ADMIN_ONLY)
async def test_endpoints_reject_regular_user(client, me, method, url, body):
    response = await client.request(method, url, json=body)

    assert response.status_code == 403, response.text


@pytest.mark.parametrize("method, url, body", SUPER_ADMIN_ONLY)
async def test_super_admin_endpoints_reject_plain_admin(client, admin_user, method, url, body):
    response = await client.request(method, url, json=body)

    assert response.status_code == 403, response.text


# --- list admins (super admin) ---


async def test_list_admins_returns_admins_but_not_regular_users(
    client, super_admin, make_user, sample_user
):
    admin_account = await make_user(role=UserRole.ADMIN)

    response = await client.get("/admin/admins")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert admin_account.id in ids
    assert sample_user.id not in ids
    assert all("password_hash" not in item for item in response.json())


# --- set role (super admin) ---


async def test_super_admin_promotes_user_to_admin(client, super_admin, sample_user):
    response = await client.put(f"/admin/users/{sample_user.id}/role", json={"role": UserRole.ADMIN.value})

    assert response.status_code == 200, response.text
    assert response.json()["id"] == sample_user.id
    assert response.json()["role"] == UserRole.ADMIN.value
    listed = await client.get("/admin/admins")
    assert sample_user.id in {item["id"] for item in listed.json()}


async def test_super_admin_demotes_admin_to_user(client, super_admin, make_user):
    admin_account = await make_user(role=UserRole.ADMIN)

    response = await client.put(f"/admin/users/{admin_account.id}/role", json={"role": UserRole.USER.value})

    assert response.status_code == 200, response.text
    assert response.json()["role"] == UserRole.USER.value


async def test_role_cannot_be_set_to_super_admin(client, super_admin, sample_user):
    response = await client.put(
        f"/admin/users/{sample_user.id}/role", json={"role": UserRole.SUPER_ADMIN.value}
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("body", [{}, {"role": "root"}, {"role": None}])
async def test_set_role_invalid_payload_returns_422(client, super_admin, sample_user, body):
    response = await client.put(f"/admin/users/{sample_user.id}/role", json=body)

    assert response.status_code == 422, response.text


async def test_set_role_of_unknown_user_returns_404(client, super_admin):
    response = await client.put("/admin/users/999999/role", json=ROLE_BODY)

    assert response.status_code == 404, response.text


async def test_super_admin_role_cannot_be_changed(client, super_admin):
    response = await client.put(f"/admin/users/{super_admin.id}/role", json=ROLE_BODY)

    assert response.status_code in (400, 403, 409), response.text


# --- list / get users (admin) ---


async def test_list_users_returns_all_users(client, admin_user, sample_user, another_user):
    response = await client.get("/admin/users")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert {sample_user.id, another_user.id, admin_user.id} <= ids
    assert all("created_at" in item for item in response.json())


async def test_list_users_respects_limit_and_offset(client, admin_user, sample_user, another_user):
    limited = await client.get("/admin/users", params={"limit": 1})
    beyond = await client.get("/admin/users", params={"offset": 1000})

    assert len(limited.json()) == 1
    assert beyond.json() == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
async def test_list_users_invalid_pagination_returns_422(client, admin_user, params):
    response = await client.get("/admin/users", params=params)

    assert response.status_code == 422, response.text


async def test_get_user_returns_admin_view(client, admin_user, sample_user):
    response = await client.get(f"/admin/users/{sample_user.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == sample_user.id
    assert body["email"] == sample_user.email
    assert body["created_at"]
    assert "password_hash" not in body


async def test_get_unknown_user_returns_404(client, admin_user):
    response = await client.get("/admin/users/999999")

    assert response.status_code == 404, response.text


# --- token limit (admin) ---


async def test_set_token_limit_updates_user(client, admin_user, sample_user):
    response = await client.put(f"/admin/users/{sample_user.id}/token-limit", json={"token_limit": 12345})

    assert response.status_code == 200, response.text
    assert response.json()["token_limit"] == 12345
    fetched = await client.get(f"/admin/users/{sample_user.id}")
    assert fetched.json()["token_limit"] == 12345


async def test_set_token_limit_to_zero_is_allowed(client, admin_user, sample_user):
    response = await client.put(f"/admin/users/{sample_user.id}/token-limit", json={"token_limit": 0})

    assert response.status_code == 200, response.text
    assert response.json()["token_limit"] == 0


@pytest.mark.parametrize("body", [{"token_limit": -1}, {"token_limit": "many"}, {}])
async def test_set_token_limit_invalid_payload_returns_422(client, admin_user, sample_user, body):
    response = await client.put(f"/admin/users/{sample_user.id}/token-limit", json=body)

    assert response.status_code == 422, response.text


async def test_set_token_limit_of_unknown_user_returns_404(client, admin_user):
    response = await client.put("/admin/users/999999/token-limit", json=TOKEN_LIMIT_BODY)

    assert response.status_code == 404, response.text


# --- reset usage (admin) ---


async def test_reset_usage_zeroes_tokens_used(client, admin_user, sample_user, sample_token_usage_event):
    response = await client.post(f"/admin/users/{sample_user.id}/reset-usage")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == sample_user.id
    assert response.json()["tokens_used"] == 0
    fetched = await client.get(f"/admin/users/{sample_user.id}")
    assert fetched.json()["tokens_used"] == 0


async def test_reset_usage_of_unknown_user_returns_404(client, admin_user):
    response = await client.post("/admin/users/999999/reset-usage")

    assert response.status_code == 404, response.text