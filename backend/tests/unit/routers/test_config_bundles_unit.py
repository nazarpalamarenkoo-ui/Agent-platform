from types import SimpleNamespace
from unittest.mock import create_autospec

import pytest

from src.api.routers import config_bundles
from src.dependencies import (
    get_bundle_export_service,
    get_config_bundle_service,
    get_effective_bundle_service,
)
from src.schemas.bundle_ops import EffectiveBundleRead
from src.schemas.config_bundle import ConfigBundleRead
from src.services.bundle_export_service import BundleExportService
from src.services.config_bundle_service import ConfigBundleService
from src.services.effective_bundle_service import EffectiveBundleService
from src.services.errors import ConflictError, NotFoundError

pytestmark = pytest.mark.unit

ROUTER = config_bundles.router
SERVICE_DEPENDENCY = get_config_bundle_service
SERVICE_SPEC = ConfigBundleService

CREATE = {
    "agent_id": 2,
    "name": "bundle",
    "description": "desc",
    "skill_ids": [1],
    "tool_ids": [2],
    "knowledge_pack_ids": [3],
}
FROM_AGENT = {"agent_id": 2, "name": "bundle", "description": "desc"}
CLONE = {"name": "copy", "description": "copy desc"}
ITEMS = {"skill_ids": [1], "tool_ids": [2], "knowledge_pack_ids": [3]}

ERRORS_404_409_400 = [
    (NotFoundError("bad"), 404),
    (ConflictError("bad"), 409),
    (ValueError("bad"), 400),
]


class TestCreate:
    async def test_returns_201_for_current_user(self, client, service, actor, fake):
        service.create_bundle.return_value = fake(ConfigBundleRead, id=11)

        response = await client.post("/config-bundles", json=CREATE)

        assert response.status_code == 201
        assert response.json()["id"] == 11
        service.create_bundle.assert_awaited_once_with(
            actor.id, 2, "bundle", "desc", [1], [2], [3]
        )

    @pytest.mark.parametrize("error,code", ERRORS_404_409_400)
    async def test_maps_errors(self, client, service, error, code):
        service.create_bundle.side_effect = error

        response = await client.post("/config-bundles", json=CREATE)

        assert response.status_code == code
        assert response.json()["detail"] == "bad"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {**CREATE, "agent_id": "abc"},
            {**CREATE, "skill_ids": "abc"},
            {**CREATE, "knowledge_pack_ids": ["x"]},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, payload):
        response = await client.post("/config-bundles", json=payload)

        assert response.status_code == 422
        service.create_bundle.assert_not_awaited()


class TestCreateFromAgent:
    async def test_returns_201(self, client, service, actor, fake):
        service.create_from_agent.return_value = fake(ConfigBundleRead, id=12)

        response = await client.post("/config-bundles/from-agent", json=FROM_AGENT)

        assert response.status_code == 201
        service.create_from_agent.assert_awaited_once_with(actor.id, 2, "bundle", "desc")

    @pytest.mark.parametrize("error,code", ERRORS_404_409_400)
    async def test_maps_errors(self, client, service, error, code):
        service.create_from_agent.side_effect = error

        response = await client.post("/config-bundles/from-agent", json=FROM_AGENT)

        assert response.status_code == code

    async def test_rejects_invalid_payload(self, client, service):
        response = await client.post("/config-bundles/from-agent", json={})

        assert response.status_code == 422
        service.create_from_agent.assert_not_awaited()


class TestListBundles:
    async def test_defaults_to_current_user(self, client, service, actor, fake):
        service.get_user_bundles.return_value = [fake(ConfigBundleRead, id=1), fake(ConfigBundleRead, id=2)]

        response = await client.get("/config-bundles")

        assert response.status_code == 200
        assert [b["id"] for b in response.json()] == [1, 2]
        service.get_user_bundles.assert_awaited_once_with(actor.id, None, limit=100, offset=0)

    async def test_passes_filters(self, client, service, actor):
        service.get_user_bundles.return_value = []

        await client.get(
            "/config-bundles", params={"agent_id": 2, "user_id": actor.id, "limit": 5, "offset": 1}
        )

        service.get_user_bundles.assert_awaited_once_with(actor.id, 2, limit=5, offset=1)

    async def test_regular_user_cannot_read_other_users_bundles(self, client, service, actor):
        response = await client.get("/config-bundles", params={"user_id": actor.id + 1})

        assert response.status_code == 403
        service.get_user_bundles.assert_not_awaited()

    async def test_admin_can_read_other_users_bundles(self, client, service, as_admin):
        service.get_user_bundles.return_value = []
        other = as_admin.id + 1

        response = await client.get("/config-bundles", params={"user_id": other})

        assert response.status_code == 200
        service.get_user_bundles.assert_awaited_once_with(other, None, limit=100, offset=0)

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
    async def test_rejects_invalid_pagination(self, client, service, params):
        response = await client.get("/config-bundles", params=params)

        assert response.status_code == 422
        service.get_user_bundles.assert_not_awaited()


class TestGetBundle:
    async def test_returns_bundle(self, client, service, actor, fake):
        service.get_bundle.return_value = fake(ConfigBundleRead, id=4)

        response = await client.get("/config-bundles/4")

        assert response.status_code == 200
        assert response.json()["id"] == 4
        service.get_bundle.assert_awaited_once_with(4, actor.id)

    async def test_not_found(self, client, service):
        service.get_bundle.side_effect = NotFoundError("nf")

        response = await client.get("/config-bundles/4")

        assert response.status_code == 404

    async def test_invalid_id(self, client, service):
        response = await client.get("/config-bundles/abc")

        assert response.status_code == 422


class TestUpdate:
    async def test_updates_name_and_description(self, client, service, actor, fake):
        service.update_bundle.return_value = fake(ConfigBundleRead, id=4)

        response = await client.patch("/config-bundles/4", json={"name": "n", "description": "d"})

        assert response.status_code == 200
        service.update_bundle.assert_awaited_once_with(4, actor.id, name="n", description="d")

    async def test_partial_update_passes_none(self, client, service, actor, fake):
        service.update_bundle.return_value = fake(ConfigBundleRead, id=4)

        await client.patch("/config-bundles/4", json={"name": "n"})

        service.update_bundle.assert_awaited_once_with(4, actor.id, name="n", description=None)

    @pytest.mark.parametrize("error,code", ERRORS_404_409_400)
    async def test_maps_errors(self, client, service, error, code):
        service.update_bundle.side_effect = error

        response = await client.patch("/config-bundles/4", json={"name": "n"})

        assert response.status_code == code


class TestDelete:
    async def test_returns_204(self, client, service, actor):
        response = await client.delete("/config-bundles/4")

        assert response.status_code == 204
        assert response.content == b""
        service.delete_bundle.assert_awaited_once_with(4, actor.id)

    async def test_not_found(self, client, service):
        service.delete_bundle.side_effect = NotFoundError("nf")

        response = await client.delete("/config-bundles/4")

        assert response.status_code == 404


class TestClone:
    async def test_returns_201(self, client, service, actor, fake):
        service.clone_bundle.return_value = fake(ConfigBundleRead, id=13)

        response = await client.post("/config-bundles/4/clone", json=CLONE)

        assert response.status_code == 201
        assert response.json()["id"] == 13
        service.clone_bundle.assert_awaited_once_with(4, actor.id, "copy", "copy desc")

    @pytest.mark.parametrize("error,code", ERRORS_404_409_400)
    async def test_maps_errors(self, client, service, error, code):
        service.clone_bundle.side_effect = error

        response = await client.post("/config-bundles/4/clone", json=CLONE)

        assert response.status_code == code

    async def test_invalid_id(self, client, service):
        response = await client.post("/config-bundles/abc/clone", json=CLONE)

        assert response.status_code == 422
        service.clone_bundle.assert_not_awaited()


class TestItems:
    async def test_add_items(self, client, service, actor, fake):
        service.add_to_bundle.return_value = fake(ConfigBundleRead, id=4)

        response = await client.post("/config-bundles/4/items", json=ITEMS)

        assert response.status_code == 200
        service.add_to_bundle.assert_awaited_once_with(
            4, actor.id, skill_ids=[1], tool_ids=[2], knowledge_pack_ids=[3]
        )

    async def test_add_items_not_found(self, client, service):
        service.add_to_bundle.side_effect = NotFoundError("nf")

        response = await client.post("/config-bundles/4/items", json=ITEMS)

        assert response.status_code == 404

    async def test_remove_items(self, client, service, actor, fake):
        service.remove_from_bundle.return_value = fake(ConfigBundleRead, id=4)

        response = await client.post("/config-bundles/4/items/remove", json=ITEMS)

        assert response.status_code == 200
        service.remove_from_bundle.assert_awaited_once_with(
            4, actor.id, skill_ids=[1], tool_ids=[2], knowledge_pack_ids=[3]
        )

    @pytest.mark.parametrize("error,code", [(NotFoundError("bad"), 404), (ConflictError("bad"), 409)])
    async def test_remove_items_maps_errors(self, client, service, error, code):
        service.remove_from_bundle.side_effect = error

        response = await client.post("/config-bundles/4/items/remove", json=ITEMS)

        assert response.status_code == code

    @pytest.mark.parametrize("path", ["items", "items/remove"])
    async def test_rejects_invalid_payload(self, client, service, path):
        response = await client.post(f"/config-bundles/4/{path}", json={"skill_ids": ["x"]})

        assert response.status_code == 422
        service.add_to_bundle.assert_not_awaited()
        service.remove_from_bundle.assert_not_awaited()


class TestEffective:
    @pytest.fixture
    def effective_service(self, override):
        return override(
            get_effective_bundle_service, create_autospec(EffectiveBundleService, instance=True)
        )

    async def test_returns_effective_bundle(self, client, service, effective_service, actor, fake):
        effective_service.get_effective_for_user.return_value = fake(EffectiveBundleRead)

        response = await client.get("/config-bundles/4/effective")

        assert response.status_code == 200
        effective_service.get_effective_for_user.assert_awaited_once_with(4, actor.id)

    async def test_not_found(self, client, service, effective_service):
        effective_service.get_effective_for_user.side_effect = NotFoundError("nf")

        response = await client.get("/config-bundles/4/effective")

        assert response.status_code == 404


class TestExport:
    @pytest.fixture
    def export_service(self, override):
        return override(get_bundle_export_service, create_autospec(BundleExportService, instance=True))

    async def test_returns_zip_with_headers(self, client, service, export_service, actor):
        export_service.build_zip.return_value = SimpleNamespace(
            content=b"PK-zip", filename="bundle.zip", version_hash="abc123"
        )

        response = await client.get("/config-bundles/4/export")

        assert response.status_code == 200
        assert response.content == b"PK-zip"
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["content-disposition"] == 'attachment; filename="bundle.zip"'
        assert response.headers["etag"] == '"abc123"'
        export_service.build_zip.assert_awaited_once_with(4, actor.id)

    async def test_not_found(self, client, service, export_service):
        export_service.build_zip.side_effect = NotFoundError("nf")

        response = await client.get("/config-bundles/4/export")

        assert response.status_code == 404