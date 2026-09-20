from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.api.routers import device
from src.db.enums.device_code_status import DeviceStatus
from src.dependencies import get_device_auth_service
from src.services.device_auth_service import DeviceAuthService

pytestmark = pytest.mark.unit

ROUTER = device.router
SERVICE_DEPENDENCY = get_device_auth_service
SERVICE_SPEC = DeviceAuthService

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_device_code(**overrides):
    data = {
        "id": 1,
        "device_code": "ABCD-1234",
        "user_code": "ABCD-1234",
        "user_id": 1,
        "scope": "read write",
        "status": DeviceStatus.PENDING,
        "expires_at": NOW + timedelta(minutes=15),
        "expires_in": 900,
        "interval": 5,
        "verification_uri": "http://testserver/device/verify",
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


async def test_initiate_flow_returns_device_code(client, service):
    service.initiate_flow.return_value = make_device_code(device_code="XYZ-999")

    response = await client.post("/device/initiate", json={"user_id": 1, "scope": "read write"})

    assert response.status_code == 200
    assert response.json()["device_code"] == "XYZ-999"
    service.initiate_flow.assert_awaited_once_with(1, "read write")


async def test_initiate_flow_value_error_returns_400(client, service):
    service.initiate_flow.side_effect = ValueError("Invalid scope")

    response = await client.post("/device/initiate", json={"user_id": 1, "scope": "bad"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid scope"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"user_id": 1},
        {"scope": "read"},
        {"user_id": "abc", "scope": "read"},
    ],
)
async def test_initiate_flow_rejects_invalid_payload(client, service, payload):
    response = await client.post("/device/initiate", json=payload)

    assert response.status_code == 422
    service.initiate_flow.assert_not_awaited()


async def test_verify_device_code_returns_access_token(client, service):
    service.verify_and_approve.return_value = "jwt-token"

    response = await client.post("/device/verify", json={"device_code": "ABCD-1234"})

    assert response.status_code == 200
    assert response.json()["access_token"] == "jwt-token"
    service.verify_and_approve.assert_awaited_once_with("ABCD-1234")


async def test_verify_device_code_value_error_returns_400(client, service):
    service.verify_and_approve.side_effect = ValueError("Invalid or expired device code")

    response = await client.post("/device/verify", json={"device_code": "nope"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired device code"


@pytest.mark.parametrize("payload", [{}, {"device_code": ["x"]}])
async def test_verify_device_code_rejects_invalid_payload(client, service, payload):
    response = await client.post("/device/verify", json=payload)

    assert response.status_code == 422
    service.verify_and_approve.assert_not_awaited()
