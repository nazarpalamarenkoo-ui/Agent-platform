import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.routers import agents
from src.db.models.agent_profiles import AgentProfile
from src.dependencies import get_agent_profile_service
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.agent_profile_service import AgentProfileService

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    service = AgentProfileService(
        AgentProfileRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
    )
    application = build_app(agents.router)
    application.dependency_overrides[get_agent_profile_service] = lambda: service
    return application


async def load_agent(db_session, agent_id):
    result = await db_session.execute(
        select(AgentProfile)
        .options(selectinload(AgentProfile.skills), selectinload(AgentProfile.tools))
        .where(AgentProfile.id == agent_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def test_create_agent_persists_skills_and_tools(client, db_session, sample_skill, sample_tool):
    payload = {
        "name": "new-agent",
        "description": "desc",
        "skill_ids": [sample_skill.id],
        "tool_ids": [sample_tool.id],
    }

    response = await client.post("/agents", json=payload)

    assert response.status_code == 201, response.text
    agent = await load_agent(db_session, response.json()["id"])
    assert [skill.id for skill in agent.skills] == [sample_skill.id]
    assert [tool.id for tool in agent.tools] == [sample_tool.id]


async def test_create_agent_without_skills_and_tools_returns_400(client):
    payload = {"name": "bare-agent", "description": "desc", "skill_ids": [], "tool_ids": []}

    response = await client.post("/agents", json=payload)

    assert response.status_code == 400, response.text


async def test_create_agent_with_unknown_skill_returns_400(client, sample_tool):
    payload = {"name": "broken", "description": "desc", "skill_ids": [999999], "tool_ids": [sample_tool.id]}

    response = await client.post("/agents", json=payload)

    assert response.status_code == 400, response.text
    assert "999999" in response.json()["detail"]


async def test_create_agent_with_unknown_tool_returns_400(client, sample_skill):
    payload = {"name": "broken", "description": "desc", "skill_ids": [sample_skill.id], "tool_ids": [999999]}

    response = await client.post("/agents", json=payload)

    assert response.status_code == 400, response.text
    assert "999999" in response.json()["detail"]


async def test_created_agent_can_be_fetched_by_id(client, sample_skill, sample_tool):
    payload = {
        "name": "fetch-me",
        "description": "desc",
        "skill_ids": [sample_skill.id],
        "tool_ids": [sample_tool.id],
    }
    created = await client.post("/agents", json=payload)
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
    response = await client.get("/agents")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert {sample_agent_profile.id, another_agent_profile.id} <= ids


async def test_get_agents_respects_limit(client, sample_agent_profile, another_agent_profile):
    response = await client.get("/agents", params={"limit": 1})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


async def test_get_agents_offset_beyond_total_returns_empty_list(client, sample_agent_profile):
    response = await client.get("/agents", params={"offset": 1000})

    assert response.status_code == 200, response.text
    assert response.json() == []