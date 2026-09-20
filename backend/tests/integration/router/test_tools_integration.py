import pytest

from src.api.routers import tools
from src.dependencies import get_tool_service
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.tool_service import ToolService

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    service = ToolService(ToolDefinitionRepository(db_session), KnowledgeDomainRepository(db_session))
    application = build_app(tools.router)
    application.dependency_overrides[get_tool_service] = lambda: service
    return application


async def test_create_tool_without_domains_returns_201(client):
    payload = {"tool_name": "calculator", "description": "Do math", "domain_ids": []}

    response = await client.post("/tools", json=payload)

    assert response.status_code == 201
    assert response.json()["id"]


async def test_create_tool_with_domains_is_listed_by_each_domain(
    client, sample_knowledge_domain, another_knowledge_domain
):
    payload = {
        "tool_name": "calculator",
        "description": "Do math",
        "domain_ids": [sample_knowledge_domain.id, another_knowledge_domain.id],
    }

    created = await client.post("/tools", json=payload)
    tool_id = created.json()["id"]

    assert created.status_code == 201
    for domain in (sample_knowledge_domain, another_knowledge_domain):
        response = await client.get(f"/tools/by-domain/{domain.id}")
        assert response.status_code == 200
        assert tool_id in {item["id"] for item in response.json()}


async def test_create_tool_duplicate_name_returns_400(client, sample_tool):
    payload = {"tool_name": sample_tool.tool_name, "description": "Other", "domain_ids": []}

    response = await client.post("/tools", json=payload)

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


async def test_create_tool_with_unknown_domain_returns_400(client):
    payload = {"tool_name": "calculator", "description": "Do math", "domain_ids": [999999]}

    response = await client.post("/tools", json=payload)

    assert response.status_code == 400
    assert "999999" in response.json()["detail"]


async def test_get_tools_returns_all_tools(client, sample_tool, another_tool):
    response = await client.get("/tools")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert {sample_tool.id, another_tool.id} <= ids


async def test_get_tools_respects_limit(client, sample_tool, another_tool):
    response = await client.get("/tools", params={"limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_get_tools_offset_beyond_total_returns_empty_list(client, sample_tool):
    response = await client.get("/tools", params={"offset": 1000})

    assert response.status_code == 200
    assert response.json() == []


async def test_get_tool_returns_existing_tool(client, sample_tool):
    response = await client.get(f"/tools/{sample_tool.id}")

    assert response.status_code == 200
    assert response.json()["id"] == sample_tool.id


async def test_get_tool_unknown_id_returns_400(client):
    response = await client.get("/tools/999999")

    assert response.status_code == 400
    assert "999999" in response.json()["detail"]


async def test_get_tools_by_domain_returns_only_tools_of_that_domain(
    client, domain_scoped_tool, sample_tool, another_knowledge_domain
):
    response = await client.get(f"/tools/by-domain/{another_knowledge_domain.id}")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert domain_scoped_tool.id in ids
    assert sample_tool.id not in ids


async def test_get_tools_by_domain_without_tools_returns_empty_list(client, sample_knowledge_domain):
    response = await client.get(f"/tools/by-domain/{sample_knowledge_domain.id}")

    assert response.status_code == 200
    assert response.json() == []
