import pytest

from src.api.routers import my_tools
from src.db.enums.tool_auth_type import ToolAuthType
from src.dependencies import get_user_tool_service
from src.schemas.user_tools import MyToolRead
from src.services.errors import ConflictError, NotFoundError
from src.services.user_tool_service import UserToolService

pytestmark = pytest.mark.unit

ROUTER = my_tools.router
SERVICE_DEPENDENCY = get_user_tool_service
SERVICE_SPEC = UserToolService

URL = "https://example.com/tool"
CREATE = {"tool_name": "my-tool", "description": "desc", "url": URL}
ERRORS = [(ValueError("bad"), 400), (NotFoundError("bad"), 404), (ConflictError("bad"), 409)]


class TestListTools:
    async def test_uses_default_pagination(self, client, service, actor, fake):
        service.list_tools.return_value = [fake(MyToolRead, id=1), fake(MyToolRead, id=2)]

        response = await client.get("/my/tools")

        assert response.status_code == 200
        assert [t["id"] for t in response.json()] == [1, 2]
        service.list_tools.assert_awaited_once_with(
            actor, limit=100, offset=0, include_archived=False
        )

    async def test_passes_query_params(self, client, service, actor):
        service.list_tools.return_value = []

        await client.get("/my/tools", params={"limit": 5, "offset": 2, "include_archived": True})

        service.list_tools.assert_awaited_once_with(actor, limit=5, offset=2, include_archived=True)

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
    async def test_rejects_invalid_pagination(self, client, service, params):
        response = await client.get("/my/tools", params=params)

        assert response.status_code == 422
        service.list_tools.assert_not_awaited()


class TestCreateTool:
    async def test_returns_201_with_tool_and_warnings(self, client, service, actor, fake):
        service.create_tool.return_value = (fake(MyToolRead, id=5), ["plain http"])

        response = await client.post("/my/tools", json=CREATE)

        assert response.status_code == 201
        body = response.json()
        assert body["tool"]["id"] == 5
        assert body["warnings"] == ["plain http"]
        service.create_tool.assert_awaited_once_with(
            actor, "my-tool", "desc", URL, ToolAuthType.NONE, None, []
        )

    async def test_passes_optional_fields(self, client, service, actor, fake):
        service.create_tool.return_value = (fake(MyToolRead, id=5), [])
        auth_type = list(ToolAuthType)[-1]

        await client.post(
            "/my/tools",
            json={**CREATE, "auth_type": auth_type.value, "auth_description": "key", "domain_ids": [1, 2]},
        )

        service.create_tool.assert_awaited_once_with(
            actor, "my-tool", "desc", URL, auth_type, "key", [1, 2]
        )

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_service_errors(self, client, service, error, code):
        service.create_tool.side_effect = error

        response = await client.post("/my/tools", json=CREATE)

        assert response.status_code == code
        assert response.json()["detail"] == "bad"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {**CREATE, "tool_name": ""},
            {**CREATE, "tool_name": "x" * 101},
            {**CREATE, "description": ""},
            {**CREATE, "description": "d" * 256},
            {**CREATE, "url": ""},
            {**CREATE, "url": "u" * 2049},
            {**CREATE, "auth_type": "not-a-type"},
            {**CREATE, "domain_ids": ["x"]},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, payload):
        response = await client.post("/my/tools", json=payload)

        assert response.status_code == 422
        service.create_tool.assert_not_awaited()


class TestGetTool:
    async def test_returns_tool(self, client, service, actor, fake):
        service.get_tool.return_value = fake(MyToolRead, id=9)

        response = await client.get("/my/tools/9")

        assert response.status_code == 200
        assert response.json()["id"] == 9
        service.get_tool.assert_awaited_once_with(actor, 9)

    async def test_not_found(self, client, service):
        service.get_tool.side_effect = NotFoundError("Tool not found")

        response = await client.get("/my/tools/9")

        assert response.status_code == 404

    async def test_invalid_id(self, client, service):
        response = await client.get("/my/tools/abc")

        assert response.status_code == 422


class TestUpdateTool:
    async def test_passes_fields_and_returns_warnings(self, client, service, actor, fake):
        service.update_tool.return_value = (fake(MyToolRead, id=3), ["leaky"])

        response = await client.put("/my/tools/3", json={"description": "new", "url": URL})

        assert response.status_code == 200
        assert response.json()["warnings"] == ["leaky"]
        service.update_tool.assert_awaited_once_with(
            actor, 3, description="new", url=URL, auth_type=None, auth_description=None
        )

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_service_errors(self, client, service, error, code):
        service.update_tool.side_effect = error

        response = await client.put("/my/tools/3", json={"description": "x"})

        assert response.status_code == code

    @pytest.mark.parametrize("payload", [{"description": ""}, {"url": ""}, {"auth_type": "nope"}])
    async def test_rejects_invalid_payload(self, client, service, payload):
        response = await client.put("/my/tools/3", json=payload)

        assert response.status_code == 422
        service.update_tool.assert_not_awaited()


class TestArchiveAndRestore:
    @pytest.mark.parametrize("action,method", [("archive", "archive_tool"), ("restore", "restore_tool")])
    async def test_calls_service(self, client, service, actor, fake, action, method):
        getattr(service, method).return_value = fake(MyToolRead, id=3)

        response = await client.post(f"/my/tools/3/{action}")

        assert response.status_code == 200
        getattr(service, method).assert_awaited_once_with(actor, 3)

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_restore_maps_errors(self, client, service, error, code):
        service.restore_tool.side_effect = error

        response = await client.post("/my/tools/3/restore")

        assert response.status_code == code