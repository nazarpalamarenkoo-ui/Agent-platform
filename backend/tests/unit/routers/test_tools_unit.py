import pytest

from src.api.routers import tools
from src.db.enums.tool_auth_type import ToolAuthType
from src.dependencies import get_tool_service
from src.schemas.tool import ToolRead
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.tool_service import ToolService

pytestmark = pytest.mark.unit

ROUTER = tools.router
SERVICE_DEPENDENCY = get_tool_service
SERVICE_SPEC = ToolService

VALID_PAYLOAD = {
    "tool_name": "web_search",
    "description": "Searching info in internet",
    "url": "https://example.com/search",
    "domain_ids": [1, 2],
}

ERRORS = [
    (NotFoundError("nf"), 404),
    (ForbiddenError("fb"), 403),
    (ConflictError("cf"), 409),
    (ValueError("bad"), 400),
]


class TestList:
    async def test_uses_defaults(self, client, service, actor, fake):
        service.list_tools.return_value = [fake(ToolRead, id=1), fake(ToolRead, id=2)]

        response = await client.get("/tools")

        assert response.status_code == 200
        assert [t["id"] for t in response.json()] == [1, 2]
        service.list_tools.assert_awaited_once_with(
            actor, limit=100, offset=0, domain_id=None, include_archived=False
        )

    async def test_passes_filters(self, client, service, actor):
        service.list_tools.return_value = []

        await client.get("/tools", params={"limit": 3, "offset": 6, "domain_id": 4, "include_archived": True})

        service.list_tools.assert_awaited_once_with(
            actor, limit=3, offset=6, domain_id=4, include_archived=True
        )

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
    async def test_rejects_invalid_pagination(self, client, service, params):
        response = await client.get("/tools", params=params)

        assert response.status_code == 422
        service.list_tools.assert_not_awaited()

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, error, code):
        service.list_tools.side_effect = error

        response = await client.get("/tools", params={"include_archived": True})

        assert response.status_code == code

    async def test_by_domain_route_is_not_shadowed_by_tool_id(self, client, service, actor, fake):
        service.list_tools.return_value = [fake(ToolRead, id=1)]

        response = await client.get("/tools/by-domain/4")

        assert response.status_code == 200
        service.list_tools.assert_awaited_once_with(actor, limit=100, offset=0, domain_id=4)
        service.get_tool.assert_not_awaited()


class TestCreate:
    async def test_admin_creates_tool_with_default_auth(self, client, service, as_admin, fake):
        service.create_tool.return_value = fake(ToolRead, id=5)

        response = await client.post("/tools", json=VALID_PAYLOAD)

        assert response.status_code == 201
        assert response.json()["id"] == 5
        service.create_tool.assert_awaited_once_with(
            as_admin, "web_search", "Searching info in internet",
            "https://example.com/search", ToolAuthType.NONE, None, [1, 2],
        )

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.post("/tools", json=VALID_PAYLOAD)

        assert response.status_code == 403
        service.create_tool.assert_not_awaited()

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, as_admin, error, code):
        service.create_tool.side_effect = error

        response = await client.post("/tools", json=VALID_PAYLOAD)

        assert response.status_code == code

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {k: v for k, v in VALID_PAYLOAD.items() if k != "url"},
            {**VALID_PAYLOAD, "auth_type": "not-an-auth-type"},
            {**VALID_PAYLOAD, "domain_ids": ["x"]},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, as_admin, payload):
        response = await client.post("/tools", json=payload)

        assert response.status_code == 422
        service.create_tool.assert_not_awaited()


class TestGet:
    async def test_returns_tool(self, client, service, actor, fake):
        service.get_tool.return_value = fake(ToolRead, id=9)

        response = await client.get("/tools/9")

        assert response.status_code == 200
        service.get_tool.assert_awaited_once_with(actor, 9)

    async def test_not_found_returns_404(self, client, service):
        service.get_tool.side_effect = NotFoundError("Tool not found")

        response = await client.get("/tools/9")

        assert response.status_code == 404

    async def test_invalid_id_returns_422(self, client, service):
        response = await client.get("/tools/abc")

        assert response.status_code == 422


class TestUpdate:
    async def test_admin_updates_tool(self, client, service, as_admin, fake):
        service.update_tool.return_value = fake(ToolRead, id=3)

        response = await client.put(
            "/tools/3", json={"description": "new", "url": "https://example.com/new", "auth_description": "key"}
        )

        assert response.status_code == 200
        service.update_tool.assert_awaited_once_with(
            as_admin, 3, description="new", url="https://example.com/new",
            auth_type=None, auth_description="key",
        )

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.put("/tools/3", json={"description": "x"})

        assert response.status_code == 403
        service.update_tool.assert_not_awaited()

    async def test_rejects_invalid_auth_type(self, client, service, as_admin):
        response = await client.put("/tools/3", json={"auth_type": "nope"})

        assert response.status_code == 422
        service.update_tool.assert_not_awaited()

    async def test_value_error_returns_400(self, client, service, as_admin):
        service.update_tool.side_effect = ValueError("Tool URL must be an absolute http(s) URL")

        response = await client.put("/tools/3", json={"url": "ftp://x"})

        assert response.status_code == 400


@pytest.mark.parametrize("action,method", [("archive", "archive_tool"), ("restore", "restore_tool")])
class TestArchiveRestore:
    async def test_admin_can_call(self, client, service, as_admin, fake, action, method):
        getattr(service, method).return_value = fake(ToolRead, id=3)

        response = await client.post(f"/tools/3/{action}")

        assert response.status_code == 200
        getattr(service, method).assert_awaited_once_with(as_admin, 3)

    async def test_regular_user_is_forbidden(self, client, service, action, method):
        response = await client.post(f"/tools/3/{action}")

        assert response.status_code == 403
        getattr(service, method).assert_not_awaited()

    async def test_not_found_returns_404(self, client, service, as_admin, action, method):
        getattr(service, method).side_effect = NotFoundError("Tool not found")

        response = await client.post(f"/tools/3/{action}")

        assert response.status_code == 404