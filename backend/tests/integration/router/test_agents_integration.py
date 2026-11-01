import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.routers import agents
from src.db.models.agent_profiles import AgentProfile
from src.dependencies import get_agent_profile_service, get_config_bundle_service
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.agent_profile_service import AgentProfileService
from src.services.config_bundle_service import ConfigBundleService

pytestmark = [pytest.mark.integration, pytest.mark.db, pytest.mark.usefixtures("default_actor")]


@pytest.fixture
def app(db_session, build_app):
    agent_service = AgentProfileService(
        AgentProfileRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
    )
    bundle_service = ConfigBundleService(
        ConfigBundleRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
        KnowledgePackRepository(db_session),
        AgentProfileRepository(db_session),
    )
    application = build_app(agents.router)
    application.dependency_overrides[get_agent_profile_service] = lambda: agent_service
    application.dependency_overrides[get_config_bundle_service] = lambda: bundle_service
    return application


@pytest.fixture(autouse=True)
def real_actor(default_actor, sample_user):
    default_actor.id = sample_user.id
    return default_actor


async def load_agent(db_session, agent_id):
    result = await db_session.execute(
        select(AgentProfile)
        .options(selectinload(AgentProfile.skills), selectinload(AgentProfile.tools))
        .where(AgentProfile.id == agent_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def agent_payload(skill_id, tool_id, **overrides):
    payload = {"name": "new-agent", "description": "desc", "skill_ids": [skill_id], "tool_ids": [tool_id]}
    payload.update(overrides)
    return payload


async def ids_of(client, **params):
    response = await client.get("/agents", params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}




async def test_create_agent_as_regular_user_returns_403(client, sample_skill, sample_tool):
    response = await client.post("/agents", json=agent_payload(sample_skill.id, sample_tool.id))

    assert response.status_code == 403, response.text


async def test_create_agent_persists_skills_and_tools(client, as_admin, db_session, sample_skill, sample_tool):
    response = await client.post("/agents", json=agent_payload(sample_skill.id, sample_tool.id))

    assert response.status_code == 201, response.text
    agent = await load_agent(db_session, response.json()["id"])
    assert [skill.id for skill in agent.skills] == [sample_skill.id]
    assert [tool.id for tool in agent.tools] == [sample_tool.id]


async def test_create_agent_without_skills_and_tools_is_allowed(client, as_admin):
    payload = {"name": "bare-agent", "description": "desc", "skill_ids": [], "tool_ids": []}

    response = await client.post("/agents", json=payload)

    assert response.status_code == 201, response.text
    assert response.json()["skills"] == []
    assert response.json()["tools"] == []


async def test_create_agent_with_unknown_skill_returns_400(client, as_admin, sample_tool):
    response = await client.post("/agents", json=agent_payload(999999, sample_tool.id, name="broken"))

    assert response.status_code in (400, 404), response.text
    assert response.json()["detail"]


async def test_create_agent_with_unknown_tool_returns_400(client, as_admin, sample_skill):
    response = await client.post("/agents", json=agent_payload(sample_skill.id, 999999, name="broken"))

    assert response.status_code in (400, 404), response.text
    assert response.json()["detail"]




async def test_created_agent_can_be_fetched_by_id(client, as_admin, sample_skill, sample_tool):
    created = await client.post("/agents", json=agent_payload(sample_skill.id, sample_tool.id, name="fetch-me"))
    assert created.status_code == 201, created.text

    response = await client.get(f"/agents/{created.json()['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == created.json()["id"]


async def test_get_agent_returns_existing_agent(client, sample_agent_profile):
    response = await client.get(f"/agents/{sample_agent_profile.id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == sample_agent_profile.id


async def test_get_agent_unknown_id_returns_404(client):
    response = await client.get("/agents/999999")

    assert response.status_code == 404, response.text


async def test_get_agents_returns_all_agents(client, sample_agent_profile, another_agent_profile):
    ids = await ids_of(client)

    assert {sample_agent_profile.id, another_agent_profile.id} <= ids


async def test_get_agents_respects_limit(client, sample_agent_profile, another_agent_profile):
    response = await client.get("/agents", params={"limit": 1})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


async def test_get_agents_offset_beyond_total_returns_empty_list(client, sample_agent_profile):
    response = await client.get("/agents", params={"offset": 1000})

    assert response.status_code == 200, response.text
    assert response.json() == []




async def test_update_agent_as_regular_user_returns_403(client, sample_agent_profile):
    response = await client.put(f"/agents/{sample_agent_profile.id}", json={"description": "Changed"})

    assert response.status_code == 403, response.text


async def test_update_agent_changes_description(client, as_admin, sample_agent_profile):
    response = await client.put(f"/agents/{sample_agent_profile.id}", json={"description": "Changed"})

    assert response.status_code == 200, response.text
    assert response.json()["description"] == "Changed"


async def test_update_agent_replaces_skills(
    client, as_admin, db_session, agent_profile_with_skill_and_tool, another_skill
):
    agent_id = agent_profile_with_skill_and_tool.id

    response = await client.put(f"/agents/{agent_id}", json={"skill_ids": [another_skill.id]})

    assert response.status_code == 200, response.text
    agent = await load_agent(db_session, agent_id)
    assert [skill.id for skill in agent.skills] == [another_skill.id]
    assert len(agent.tools) == 1


async def test_update_agent_with_unknown_skill_returns_400(client, as_admin, sample_agent_profile):
    response = await client.put(f"/agents/{sample_agent_profile.id}", json={"skill_ids": [999999]})

    assert response.status_code in (400, 404), response.text
    assert response.json()["detail"]


async def test_update_unknown_agent_is_rejected(client, as_admin, assert_missing):
    assert_missing(await client.put("/agents/999999", json={"description": "Changed"}))




async def test_archive_agent_as_regular_user_returns_403(client, sample_agent_profile):
    response = await client.post(f"/agents/{sample_agent_profile.id}/archive")

    assert response.status_code == 403, response.text


async def test_restore_agent_as_regular_user_returns_403(client, sample_agent_profile):
    response = await client.post(f"/agents/{sample_agent_profile.id}/restore")

    assert response.status_code == 403, response.text


async def test_archived_agent_is_hidden_unless_include_archived(client, as_admin, sample_agent_profile):
    response = await client.post(f"/agents/{sample_agent_profile.id}/archive")

    assert response.status_code == 200, response.text
    assert sample_agent_profile.id not in await ids_of(client)
    assert sample_agent_profile.id in await ids_of(client, include_archived=True)


async def test_restore_agent_makes_it_visible_again(client, as_admin, sample_agent_profile):
    await client.post(f"/agents/{sample_agent_profile.id}/archive")

    response = await client.post(f"/agents/{sample_agent_profile.id}/restore")

    assert response.status_code == 200, response.text
    assert sample_agent_profile.id in await ids_of(client)


async def test_archive_unknown_agent_is_rejected(client, as_admin, assert_missing):
    assert_missing(await client.post("/agents/999999/archive"))




def custom_payload(**overrides):
    payload = {
        "name": "my-custom-agent",
        "description": "desc",
        "skill_ids": [],
        "tool_ids": [],
        "knowledge_pack_ids": [],
    }
    payload.update(overrides)
    return payload


@pytest_asyncio.fixture
async def neutral_agent(make_agent):
    return await make_agent(agent_name="neutral", is_neutral=True)


async def test_create_custom_agent_as_regular_user_returns_201(
    client, neutral_agent, sample_skill, sample_tool, sample_knowledge_pack
):
    payload = custom_payload(
        skill_ids=[sample_skill.id],
        tool_ids=[sample_tool.id],
        knowledge_pack_ids=[sample_knowledge_pack.id],
    )

    response = await client.post("/agents/custom", json=payload)

    assert response.status_code == 201, response.text
    assert response.json()["id"]


async def test_create_custom_agent_without_items_is_allowed(client, neutral_agent):
    response = await client.post("/agents/custom", json=custom_payload())

    assert response.status_code == 201, response.text
    assert response.json()["id"]


@pytest.mark.parametrize(
    "field, expected",
    [("skill_ids", "Skill"), ("tool_ids", "Tool"), ("knowledge_pack_ids", "Knowledge pack")],
)
async def test_create_custom_agent_with_unknown_item_returns_400(
    client, neutral_agent, sample_skill, field, expected
):
    payload = custom_payload(**{"skill_ids": [sample_skill.id], field: [999999]})

    response = await client.post("/agents/custom", json=payload)

    assert response.status_code in (400, 404), response.text
    assert response.json()["detail"]