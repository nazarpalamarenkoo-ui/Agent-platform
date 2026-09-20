import pytest

from src.api.routers import tools
from src.dependencies import get_tool_service
from src.services.tool_service import ToolService
from src.schemas.tool import ToolRead

pytestmark = pytest.mark.unit

ROUTER = tools.router
SERVICE_DEPENDENCY = get_tool_service
SERVICE_SPEC = ToolService

VALID_PAYLOAD = {
    "tool_name": "web_search",
    "description": "Searching info in internet",
    "domain_ids": [1, 2],
}


async def test_create_tool_returns_201(client, service, fake):
    service.create_tool.return_value = fake(ToolRead, id=5)

    response = await client.post("/tools", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["id"] == 5
    service.create_tool.assert_awaited_once_with("web_search", "Searching info in internet", [1, 2])


async def test_create_tool_value_error_returns_400(client, service):
    service.create_tool.side_effect = ValueError("Tool 'web_search' already exists")

    response = await client.post("/tools", json=VALID_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Tool 'web_search' already exists"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**VALID_PAYLOAD, "tool_name": ["x"]},
        {**VALID_PAYLOAD, "domain_ids": "abc"},
        {**VALID_PAYLOAD, "domain_ids": ["x"]},
    ],
)
async def test_create_tool_rejects_invalid_payload(client, service, payload):
    response = await client.post("/tools", json=payload)

    assert response.status_code == 422
    service.create_tool.assert_not_awaited()


async def test_get_tools_uses_default_pagination(client, service, fake):
    service.get_all_tools.return_value = [fake(ToolRead, id=1), fake(ToolRead, id=2)]

    response = await client.get("/tools")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1, 2]
    service.get_all_tools.assert_awaited_once_with(100, 0)


async def test_get_tools_passes_custom_pagination(client, service):
    service.get_all_tools.return_value = []

    response = await client.get("/tools", params={"limit": 3, "offset": 6})

    assert response.status_code == 200
    service.get_all_tools.assert_awaited_once_with(3, 6)


async def test_get_tools_value_error_returns_400(client, service):
    service.get_all_tools.side_effect = ValueError("bad pagination")

    response = await client.get("/tools")

    assert response.status_code == 400
    assert response.json()["detail"] == "bad pagination"


@pytest.mark.parametrize("params", [{"limit": "abc"}, {"offset": "abc"}])
async def test_get_tools_rejects_invalid_pagination(client, service, params):
    response = await client.get("/tools", params=params)

    assert response.status_code == 422
    service.get_all_tools.assert_not_awaited()


async def test_get_tool_returns_tool(client, service, fake):
    service.get_tool.return_value = fake(ToolRead, id=9)

    response = await client.get("/tools/9")

    assert response.status_code == 200
    assert response.json()["id"] == 9
    service.get_tool.assert_awaited_once_with(9)


async def test_get_tool_value_error_returns_400(client, service):
    service.get_tool.side_effect = ValueError("Tool 9 not found")

    response = await client.get("/tools/9")

    assert response.status_code == 400
    assert response.json()["detail"] == "Tool 9 not found"


async def test_get_tool_invalid_id_returns_422(client, service):
    response = await client.get("/tools/abc")

    assert response.status_code == 422
    service.get_tool.assert_not_awaited()


async def test_get_tools_by_domain_returns_list(client, service, fake):
    service.get_tools_by_domain.return_value = [fake(ToolRead, id=1)]

    response = await client.get("/tools/by-domain/4")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1]
    service.get_tools_by_domain.assert_awaited_once_with(4)
    service.get_tool.assert_not_awaited()


async def test_get_tools_by_domain_value_error_returns_400(client, service):
    service.get_tools_by_domain.side_effect = ValueError("Domain 4 not found")

    response = await client.get("/tools/by-domain/4")

    assert response.status_code == 400
    assert response.json()["detail"] == "Domain 4 not found"


async def test_get_tools_by_domain_invalid_id_returns_422(client, service):
    response = await client.get("/tools/by-domain/abc")

    assert response.status_code == 422
    service.get_tools_by_domain.assert_not_awaited()