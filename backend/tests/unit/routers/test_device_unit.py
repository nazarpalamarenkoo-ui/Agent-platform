from unittest.mock import create_autospec

import pytest

from src.api.routers import device
from src.dependencies import get_config_bundle_service, get_device_auth_service
from src.schemas.device import DeviceRead
from src.services.config_bundle_service import ConfigBundleService
from src.services.device_auth_service import DeviceAuthService
from src.services.errors import NotFoundError

pytestmark = pytest.mark.unit

ROUTER = device.router
SERVICE_DEPENDENCY = get_device_auth_service
SERVICE_SPEC = DeviceAuthService

CREATE = {"scope": "read write"}


@pytest.fixture
def bundle_service(override):
    return override(get_config_bundle_service, create_autospec(ConfigBundleService, instance=True))


class TestIssueToken:
    async def test_returns_201_with_token(self, client, service, bundle_service, actor, fake):
        service.issue_token.return_value = (fake(DeviceRead, id=3, name="device"), "jwt-token")

        response = await client.post("/device/tokens", json=CREATE)

        assert response.status_code == 201
        body = response.json()
        assert body["id"] == 3
        assert body["access_token"] == "jwt-token"
        assert body["token_type"] == "bearer"
        service.issue_token.assert_awaited_once_with(actor.id, "read write", "device", None)
        bundle_service.get_bundle.assert_not_awaited()

    async def test_checks_bundle_ownership(self, client, service, bundle_service, actor, fake):
        service.issue_token.return_value = (fake(DeviceRead, id=3), "jwt-token")

        response = await client.post(
            "/device/tokens", json={**CREATE, "name": "laptop", "config_bundle_id": 7}
        )

        assert response.status_code == 201
        bundle_service.get_bundle.assert_awaited_once_with(7, actor.id)
        service.issue_token.assert_awaited_once_with(actor.id, "read write", "laptop", 7)

    async def test_foreign_bundle_returns_404_and_no_token(self, client, service, bundle_service):
        bundle_service.get_bundle.side_effect = NotFoundError("nf")

        response = await client.post("/device/tokens", json={**CREATE, "config_bundle_id": 7})

        assert response.status_code == 404
        service.issue_token.assert_not_awaited()

    async def test_value_error_returns_400(self, client, service, bundle_service):
        service.issue_token.side_effect = ValueError("bad")

        response = await client.post("/device/tokens", json=CREATE)

        assert response.status_code == 400
        assert response.json()["detail"] == "bad"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"scope": ""},
            {"scope": "x" * 101},
            {"scope": "Read"},
            {"scope": "read  write"},
            {"scope": " read"},
            {"scope": "read,write"},
            {"scope": ["x"]},
            {**CREATE, "name": ""},
            {**CREATE, "name": "x" * 101},
            {**CREATE, "config_bundle_id": "abc"},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, bundle_service, payload):
        response = await client.post("/device/tokens", json=payload)

        assert response.status_code == 422
        service.issue_token.assert_not_awaited()


class TestListDevices:
    async def test_uses_defaults(self, client, service, actor, fake):
        service.list_devices.return_value = [fake(DeviceRead, id=1), fake(DeviceRead, id=2)]

        response = await client.get("/device")

        assert response.status_code == 200
        assert [d["id"] for d in response.json()] == [1, 2]
        assert "access_token" not in response.json()[0]
        service.list_devices.assert_awaited_once_with(
            actor.id, active_only=True, limit=100, offset=0
        )

    async def test_passes_query_params(self, client, service, actor):
        service.list_devices.return_value = []

        await client.get("/device", params={"active_only": False, "limit": 5, "offset": 2})

        service.list_devices.assert_awaited_once_with(
            actor.id, active_only=False, limit=5, offset=2
        )

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
    async def test_rejects_invalid_pagination(self, client, service, params):
        response = await client.get("/device", params=params)

        assert response.status_code == 422
        service.list_devices.assert_not_awaited()


class TestRevoke:
    async def test_revokes_own_device(self, client, service, actor, fake):
        service.revoke_device.return_value = fake(DeviceRead, id=4)

        response = await client.post("/device/4/revoke")

        assert response.status_code == 200
        assert response.json()["id"] == 4
        service.revoke_device.assert_awaited_once_with(actor.id, 4)

    async def test_not_found(self, client, service):
        service.revoke_device.side_effect = NotFoundError("Device not found")

        response = await client.post("/device/4/revoke")

        assert response.status_code == 404
        assert response.json()["detail"] == "Device not found"

    async def test_invalid_id(self, client, service):
        response = await client.post("/device/abc/revoke")

        assert response.status_code == 422
        service.revoke_device.assert_not_awaited()