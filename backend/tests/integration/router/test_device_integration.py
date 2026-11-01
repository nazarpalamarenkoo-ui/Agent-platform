from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.api.auth import auth as main_auth
from src.api.auth.admin import auth as admin_auth
from src.api.routers import device
from src.db.db_connection import get_db
from src.db.models.device_code import DeviceCode

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    application = build_app(device.router)
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


def token_payload(**overrides):
    payload = {"scope": "read write", "name": "laptop"}
    payload.update(overrides)
    return payload


def parse_moment(value):
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


async def device_ids(client, **params):
    response = await client.get("/device", params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


@pytest.mark.parametrize(
    "method, url",
    [
        ("POST", "/device/tokens"),
        ("GET", "/device"),
        ("POST", "/device/1/revoke"),
    ],
)
async def test_endpoints_require_authentication(client, method, url):
    response = await client.request(method, url)

    assert response.status_code == 401, response.text


# --- issue token ---


async def test_issue_token_returns_secret_and_metadata(client, me):
    response = await client.post("/device/tokens", json=token_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"]
    assert body["name"] == "laptop"
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["config_bundle_id"] is None
    assert parse_moment(body["expires_at"]) > datetime.now(timezone.utc)


async def test_issue_token_uses_default_name(client, me):
    response = await client.post("/device/tokens", json={"scope": "read"})

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "device"


async def test_issue_token_generates_unique_secrets(client, me):
    first = await client.post("/device/tokens", json=token_payload())
    second = await client.post("/device/tokens", json=token_payload())

    assert first.json()["access_token"] != second.json()["access_token"]
    assert first.json()["id"] != second.json()["id"]


async def test_issued_token_is_stored_only_as_hash(client, me, db_session):
    response = await client.post("/device/tokens", json=token_payload())
    body = response.json()

    row = await db_session.get(DeviceCode, body["id"])

    assert row.user_id == me.id
    assert row.token_hash != body["access_token"]
    assert body["access_token"] not in str(row.token_hash)


async def test_issue_token_bound_to_own_bundle(client, me, sample_config_bundle):
    response = await client.post(
        "/device/tokens", json=token_payload(config_bundle_id=sample_config_bundle.id)
    )

    assert response.status_code == 201, response.text
    assert response.json()["config_bundle_id"] == sample_config_bundle.id


async def test_issue_token_for_foreign_bundle_returns_404(
    client, me, another_user, sample_agent_profile, make_bundle, db_session
):
    foreign = await make_bundle(another_user, sample_agent_profile)

    response = await client.post("/device/tokens", json=token_payload(config_bundle_id=foreign.id))

    assert response.status_code == 404, response.text
    issued = await db_session.execute(select(DeviceCode).where(DeviceCode.user_id == me.id))
    assert issued.scalars().all() == []


async def test_issue_token_for_unknown_bundle_returns_404(client, me):
    response = await client.post("/device/tokens", json=token_payload(config_bundle_id=999999))

    assert response.status_code == 404, response.text


@pytest.mark.parametrize("scope", ["read", "read write", "offline_access", "skills:read tools.read", "a-b_c"])
async def test_issue_token_accepts_valid_scopes(client, me, scope):
    response = await client.post("/device/tokens", json=token_payload(scope=scope))

    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"scope": ""},
        {"scope": "READ"},
        {"scope": "read  write"},
        {"scope": " read"},
        {"scope": "read "},
        {"scope": "bad scope!"},
        {"scope": "a" * 101},
        {"name": ""},
        {"name": "x" * 101},
        {"config_bundle_id": "not-a-number"},
    ],
)
async def test_issue_token_invalid_payload_returns_422(client, me, overrides):
    response = await client.post("/device/tokens", json=token_payload(**overrides))

    assert response.status_code == 422, response.text


async def test_issue_token_without_scope_returns_422(client, me):
    response = await client.post("/device/tokens", json={"name": "laptop"})

    assert response.status_code == 422, response.text


# --- list ---


async def test_list_devices_never_exposes_token_secret(client, me):
    issued = await client.post("/device/tokens", json=token_payload())

    response = await client.get("/device")

    assert response.status_code == 200, response.text
    assert issued.json()["access_token"] not in response.text
    assert all("access_token" not in item and "token_hash" not in item for item in response.json())


async def test_list_returns_only_own_devices(client, me, another_user, make_device_code):
    mine = await make_device_code(user=me)
    foreign = await make_device_code(user=another_user)

    ids = await device_ids(client)

    assert mine.id in ids
    assert foreign.id not in ids


async def test_list_hides_revoked_devices_unless_active_only_is_false(client, me, make_device_code):
    device_row = await make_device_code(user=me)
    await client.post(f"/device/{device_row.id}/revoke")

    assert device_row.id not in await device_ids(client)
    assert device_row.id not in await device_ids(client, active_only=True)
    assert device_row.id in await device_ids(client, active_only=False)


async def test_list_respects_limit_and_offset(client, me, make_device_code):
    await make_device_code(user=me)
    await make_device_code(user=me)

    limited = await client.get("/device", params={"limit": 1})
    beyond = await client.get("/device", params={"offset": 1000})

    assert len(limited.json()) == 1
    assert beyond.json() == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
async def test_list_invalid_pagination_returns_422(client, me, params):
    response = await client.get("/device", params=params)

    assert response.status_code == 422, response.text


# --- revoke ---


async def test_revoke_device_returns_device(client, me, make_device_code):
    device_row = await make_device_code(user=me)

    response = await client.post(f"/device/{device_row.id}/revoke")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == device_row.id
    assert response.json()["name"] == device_row.name


async def test_revoke_foreign_device_is_rejected_and_keeps_it_active(
    client, me, another_user, make_device_code, login
):
    foreign = await make_device_code(user=another_user)

    response = await client.post(f"/device/{foreign.id}/revoke")

    assert response.status_code in (403, 404), response.text
    login(another_user)
    assert foreign.id in await device_ids(client)


async def test_revoke_unknown_device_returns_404(client, me):
    response = await client.post("/device/999999/revoke")

    assert response.status_code == 404, response.text