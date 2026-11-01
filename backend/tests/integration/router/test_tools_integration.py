import pytest

from src.api.routers import tools
from src.dependencies import get_tool_service
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.notification_repo import NotificationRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.tool_service import ToolService

pytestmark = [pytest.mark.integration, pytest.mark.db, pytest.mark.usefixtures("default_actor")]


@pytest.fixture
def app(db_session, build_app):
    service = ToolService(
        ToolDefinitionRepository(db_session),
        KnowledgeDomainRepository(db_session),
        ConfigBundleRepository(db_session),
        NotificationRepository(db_session),
    )
    application = build_app(tools.router)
    application.dependency_overrides[get_tool_service] = lambda: service
    return application


def tool_payload(**overrides):
    payload = {
        "tool_name": "calculator",
        "description": "Do math",
        "url": "https://example.com/calculator",
        "domain_ids": [],
    }
    payload.update(overrides)
    return payload


async def ids_of(client, url="/tools", **params):
    response = await client.get(url, params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


# --- create (admin only) ---


async def test_create_tool_as_regular_user_returns_403(client):
    response = await client.post("/tools", json=tool_payload())

    assert response.status_code == 403, response.text


async def test_create_tool_without_domains_returns_201(client, as_admin):
    response = await client.post("/tools", json=tool_payload())

    assert response.status_code == 201, response.text
    assert response.json()["id"]


async def test_create_tool_with_domains_is_listed_by_each_domain(
    client, as_admin, sample_knowledge_domain, another_knowledge_domain
):
    payload = tool_payload(domain_ids=[sample_knowledge_domain.id, another_knowledge_domain.id])

    created = await client.post("/tools", json=payload)
    assert created.status_code == 201, created.text

    for domain in (sample_knowledge_domain, another_knowledge_domain):
        assert created.json()["id"] in await ids_of(client, f"/tools/by-domain/{domain.id}")


async def test_create_tool_duplicate_name_returns_400(client, as_admin, sample_tool):
    response = await client.post("/tools", json=tool_payload(tool_name=sample_tool.tool_name))

    assert response.status_code in (400, 409), response.text
    assert "already exists" in response.json()["detail"]


async def test_create_tool_with_unknown_domain_returns_400(client, as_admin):
    response = await client.post("/tools", json=tool_payload(domain_ids=[999999]))

    assert response.status_code in (400, 404), response.text
    assert "999999" in response.json()["detail"]


# --- read ---


async def test_get_tools_returns_all_tools(client, sample_tool, another_tool):
    ids = await ids_of(client)

    assert {sample_tool.id, another_tool.id} <= ids


async def test_get_tools_respects_limit(client, sample_tool, another_tool):
    response = await client.get("/tools", params={"limit": 1})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


async def test_get_tools_offset_beyond_total_returns_empty_list(client, sample_tool):
    response = await client.get("/tools", params={"offset": 1000})

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_get_tools_filters_by_domain_query_param(
    client, domain_scoped_tool, sample_tool, another_knowledge_domain
):
    ids = await ids_of(client, domain_id=another_knowledge_domain.id)

    assert domain_scoped_tool.id in ids
    assert sample_tool.id not in ids


async def test_get_tool_returns_existing_tool(client, sample_tool):
    response = await client.get(f"/tools/{sample_tool.id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == sample_tool.id


async def test_get_unknown_tool_is_rejected(client, assert_missing):
    assert_missing(await client.get("/tools/999999"))


async def test_get_tools_by_domain_returns_only_tools_of_that_domain(
    client, domain_scoped_tool, sample_tool, another_knowledge_domain
):
    ids = await ids_of(client, f"/tools/by-domain/{another_knowledge_domain.id}")

    assert domain_scoped_tool.id in ids
    assert sample_tool.id not in ids


async def test_get_tools_by_domain_without_tools_returns_empty_list(client, sample_knowledge_domain):
    response = await client.get(f"/tools/by-domain/{sample_knowledge_domain.id}")

    assert response.status_code == 200, response.text
    assert response.json() == []


# --- update (admin only) ---


async def test_update_tool_as_regular_user_returns_403(client, sample_tool):
    response = await client.put(f"/tools/{sample_tool.id}", json={"description": "Changed"})

    assert response.status_code == 403, response.text


async def test_update_tool_changes_description_and_url(client, as_admin, sample_tool):
    response = await client.put(
        f"/tools/{sample_tool.id}",
        json={"description": "Changed", "url": "https://example.com/v2"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["description"] == "Changed"
    fetched = await client.get(f"/tools/{sample_tool.id}")
    assert fetched.json()["description"] == "Changed"


async def test_update_unknown_tool_is_rejected(client, as_admin, assert_missing):
    assert_missing(await client.put("/tools/999999", json={"description": "Changed"}))


# --- archive / restore (admin only) ---


async def test_archive_tool_as_regular_user_returns_403(client, sample_tool):
    response = await client.post(f"/tools/{sample_tool.id}/archive")

    assert response.status_code == 403, response.text


async def test_restore_tool_as_regular_user_returns_403(client, sample_tool):
    response = await client.post(f"/tools/{sample_tool.id}/restore")

    assert response.status_code == 403, response.text


async def test_archived_tool_is_hidden_unless_include_archived(client, as_admin, sample_tool):
    response = await client.post(f"/tools/{sample_tool.id}/archive")

    assert response.status_code == 200, response.text
    assert sample_tool.id not in await ids_of(client)
    assert sample_tool.id in await ids_of(client, include_archived=True)


async def test_restore_tool_makes_it_visible_again(client, as_admin, sample_tool):
    await client.post(f"/tools/{sample_tool.id}/archive")

    response = await client.post(f"/tools/{sample_tool.id}/restore")

    assert response.status_code == 200, response.text
    assert sample_tool.id in await ids_of(client)


async def test_archive_unknown_tool_is_rejected(client, as_admin, assert_missing):
    assert_missing(await client.post("/tools/999999/archive"))