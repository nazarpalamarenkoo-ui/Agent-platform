import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.routers import config_bundles
from src.db.models.config_bundles import ConfigBundle
from src.dependencies import get_config_bundle_service
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.config_bundle_service import ConfigBundleService

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    service = ConfigBundleService(
        ConfigBundleRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
        KnowledgePackRepository(db_session),
        AgentProfileRepository(db_session),
    )
    application = build_app(config_bundles.router)
    application.dependency_overrides[get_config_bundle_service] = lambda: service
    return application


async def load_bundle(db_session, bundle_id):
    result = await db_session.execute(
        select(ConfigBundle)
        .options(
            selectinload(ConfigBundle.skills),
            selectinload(ConfigBundle.tools),
            selectinload(ConfigBundle.knowledge_packs),
        )
        .where(ConfigBundle.id == bundle_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def create_payload(agent_id, **overrides):
    payload = {
        "agent_id": agent_id,
        "name": "new-bundle",
        "description": "desc",
        "skill_ids": [],
        "tool_ids": [],
        "knowledge_pack_ids": [],
    }
    payload.update(overrides)
    return payload


async def test_create_bundle_persists_relations(
    client, db_session, sample_user, sample_agent_profile, sample_skill, sample_tool, sample_knowledge_pack
):
    payload = create_payload(
        sample_agent_profile.id,
        skill_ids=[sample_skill.id],
        tool_ids=[sample_tool.id],
        knowledge_pack_ids=[sample_knowledge_pack.id],
    )

    response = await client.post("/config-bundles", params={"user_id": sample_user.id}, json=payload)

    assert response.status_code == 201, response.text
    bundle = await load_bundle(db_session, response.json()["id"])
    assert bundle.user_id == sample_user.id
    assert bundle.agent_id == sample_agent_profile.id
    assert [skill.id for skill in bundle.skills] == [sample_skill.id]
    assert [tool.id for tool in bundle.tools] == [sample_tool.id]
    assert [pack.id for pack in bundle.knowledge_packs] == [sample_knowledge_pack.id]


async def test_create_bundle_without_relations_returns_400(client, sample_user, sample_agent_profile):
    response = await client.post(
        "/config-bundles", params={"user_id": sample_user.id}, json=create_payload(sample_agent_profile.id)
    )

    assert response.status_code == 400, response.text


@pytest.mark.parametrize(
    "field, expected",
    [
        ("skill_ids", "Skill"),
        ("tool_ids", "Tool"),
        ("knowledge_pack_ids", "Knowledge pack"),
    ],
)
async def test_create_bundle_with_unknown_relation_returns_400(
    client, sample_user, sample_agent_profile, field, expected
):
    payload = create_payload(sample_agent_profile.id, **{field: [999999]})

    response = await client.post("/config-bundles", params={"user_id": sample_user.id}, json=payload)

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert expected in detail
    assert "999999" in detail


async def test_create_from_agent_returns_400(client, sample_user, agent_profile_with_skill_and_tool):
    payload = {"agent_id": agent_profile_with_skill_and_tool.id, "name": "from-agent", "description": "desc"}

    response = await client.post(
        "/config-bundles/from-agent", params={"user_id": sample_user.id}, json=payload
    )

    assert response.status_code == 400, response.text


async def test_create_from_agent_unknown_agent_returns_400(client, sample_user):
    payload = {"agent_id": 999999, "name": "from-agent", "description": "desc"}

    response = await client.post(
        "/config-bundles/from-agent", params={"user_id": sample_user.id}, json=payload
    )

    assert response.status_code == 400, response.text
    assert "999999" in response.json()["detail"]


async def test_clone_bundle_copies_all_relations_for_another_user(
    client,
    db_session,
    another_user,
    config_bundle_with_skill_and_tool,
    config_bundle_with_knowledge_pack,
    sample_skill,
    sample_tool,
    sample_knowledge_pack,
):
    original = config_bundle_with_knowledge_pack

    response = await client.post(f"/config-bundles/{original.id}/clone", params={"user_id": another_user.id})

    assert response.status_code == 201, response.text
    cloned = await load_bundle(db_session, response.json()["id"])
    assert cloned.id != original.id
    assert cloned.user_id == another_user.id
    assert cloned.agent_id == original.agent_id
    assert cloned.name == f"Clone of {original.name}"
    assert [skill.id for skill in cloned.skills] == [sample_skill.id]
    assert [tool.id for tool in cloned.tools] == [sample_tool.id]
    assert [pack.id for pack in cloned.knowledge_packs] == [sample_knowledge_pack.id]


async def test_clone_bundle_does_not_modify_original(
    client, db_session, another_user, config_bundle_with_skill_and_tool
):
    original_id = config_bundle_with_skill_and_tool.id

    await client.post(f"/config-bundles/{original_id}/clone", params={"user_id": another_user.id})

    original = await load_bundle(db_session, original_id)
    assert original.name == "default-bundle"
    assert len(original.skills) == 1
    assert len(original.tools) == 1


async def test_clone_unknown_bundle_returns_400(client, sample_user):
    response = await client.post("/config-bundles/999999/clone", params={"user_id": sample_user.id})

    assert response.status_code == 400, response.text
    assert "999999" in response.json()["detail"]


async def test_get_user_bundles_returns_bundles_of_user_and_agent(
    client, sample_user, sample_agent_profile, sample_config_bundle
):
    response = await client.get(
        "/config-bundles", params={"user_id": sample_user.id, "agent_id": sample_agent_profile.id}
    )

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [sample_config_bundle.id]


async def test_get_user_bundles_excludes_other_users(
    client, another_user, sample_agent_profile, sample_config_bundle
):
    response = await client.get(
        "/config-bundles", params={"user_id": another_user.id, "agent_id": sample_agent_profile.id}
    )

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_get_user_bundles_excludes_other_agents(
    client, sample_user, another_agent_profile, sample_config_bundle
):
    response = await client.get(
        "/config-bundles", params={"user_id": sample_user.id, "agent_id": another_agent_profile.id}
    )

    assert response.status_code == 200, response.text
    assert response.json() == []