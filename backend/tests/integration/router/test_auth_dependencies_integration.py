"""The real get_current_user / require_admin chain, with no dependency overrides except the DB."""
from datetime import timedelta

import pytest
from jose import jwt

from src.api.auth.auth import (
    ALGORITHM,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_PASSWORD_RESET,
    create_access_token,
    create_token,
)
from src.api.routers import admin, users
from src.db.db_connection import get_db
from src.db.enums.user_role import UserRole

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    application = build_app(users.router)
    application.include_router(admin.router)
    application.dependency_overrides[get_db] = lambda: db_session
    return application


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def test_valid_access_token_authenticates_user(client, sample_user):
    response = await client.get("/users/me", headers=bearer(create_access_token(sample_user.id)))

    assert response.status_code == 200, response.text
    assert response.json()["id"] == sample_user.id


async def test_missing_token_returns_401_with_bearer_challenge(client):
    response = await client.get("/users/me")

    assert response.status_code == 401, response.text
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["garbage", "a.b.c", ""])
async def test_malformed_token_returns_401(client, token):
    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 401, response.text


async def test_expired_token_returns_401(client, sample_user):
    token = create_token(str(sample_user.id), TOKEN_TYPE_ACCESS, timedelta(minutes=-1))

    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 401, response.text


async def test_token_signed_with_other_secret_returns_401(client, sample_user):
    token = jwt.encode({"sub": str(sample_user.id), "typ": TOKEN_TYPE_ACCESS}, "other-secret", algorithm=ALGORITHM)

    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 401, response.text


async def test_token_of_other_type_is_not_accepted_as_access_token(client, sample_user):
    token = create_token(str(sample_user.id), TOKEN_TYPE_PASSWORD_RESET, timedelta(hours=1))

    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 401, response.text


async def test_token_with_non_numeric_subject_returns_401(client):
    token = create_token("not-a-number", TOKEN_TYPE_ACCESS, timedelta(hours=1))

    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 401, response.text


async def test_token_of_deleted_user_returns_401(client):
    response = await client.get("/users/me", headers=bearer(create_access_token(999999)))

    assert response.status_code == 401, response.text


async def test_admin_route_rejects_regular_user_token(client, sample_user):
    response = await client.get("/admin/users", headers=bearer(create_access_token(sample_user.id)))

    assert response.status_code == 403, response.text


async def test_admin_route_accepts_admin_token(client, make_user):
    admin_account = await make_user(role=UserRole.ADMIN)

    response = await client.get("/admin/users", headers=bearer(create_access_token(admin_account.id)))

    assert response.status_code == 200, response.text


async def test_super_admin_route_rejects_plain_admin_token(client, make_user):
    admin_account = await make_user(role=UserRole.ADMIN)

    response = await client.get("/admin/admins", headers=bearer(create_access_token(admin_account.id)))

    assert response.status_code == 403, response.text


async def test_super_admin_route_accepts_super_admin_token(client, make_user):
    super_admin = await make_user(role=UserRole.SUPER_ADMIN)

    response = await client.get("/admin/admins", headers=bearer(create_access_token(super_admin.id)))

    assert response.status_code == 200, response.text