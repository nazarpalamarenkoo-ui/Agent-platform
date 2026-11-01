import io
import json
import zipfile

import pytest

from src.api.routers import config_bundles
from src.db.db_connection import get_db
from src.dependencies import (
    get_bundle_export_service,
    get_config_bundle_service,
    get_effective_bundle_service,
)
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.bundle_export_service import BundleExportService
from src.services.config_bundle_service import ConfigBundleService
from src.services.effective_bundle_service import EffectiveBundleService

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    bundle_repo = ConfigBundleRepository(db_session)
    skill_repo = SkillRepository(db_session)
    tool_repo = ToolDefinitionRepository(db_session)
    pack_repo = KnowledgePackRepository(db_session)
    agent_repo = AgentProfileRepository(db_session)

    bundle_service = ConfigBundleService(bundle_repo, skill_repo, tool_repo, pack_repo, agent_repo)
    effective_service = EffectiveBundleService(bundle_repo, skill_repo, tool_repo, pack_repo, agent_repo)
    export_service = BundleExportService(bundle_repo, skill_repo, effective_service)

    application = build_app(config_bundles.router)
    application.dependency_overrides[get_db] = lambda: db_session
    application.dependency_overrides[get_config_bundle_service] = lambda: bundle_service
    application.dependency_overrides[get_effective_bundle_service] = lambda: effective_service
    application.dependency_overrides[get_bundle_export_service] = lambda: export_service
    return application


@pytest.fixture(autouse=True)
def real_actor(default_actor, sample_user):
    default_actor.id = sample_user.id
    return default_actor


def ids(items):
    return [item["id"] for item in items]


def create_payload(agent_id, **overrides):
    payload = {
        "agent_id": agent_id,
        "name": "my-bundle",
        "description": "desc",
        "skill_ids": [],
        "tool_ids": [],
        "knowledge_pack_ids": [],
    }
    payload.update(overrides)
    return payload


def items_payload(**overrides):
    payload = {"skill_ids": [], "tool_ids": [], "knowledge_pack_ids": []}
    payload.update(overrides)
    return payload


async def create_bundle(client, agent_id, **overrides):
    response = await client.post("/config-bundles", json=create_payload(agent_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_bundle_persists_selected_items(
    client, sample_agent_profile, sample_skill, sample_tool, sample_knowledge_pack
):
    body = await create_bundle(
        client,
        sample_agent_profile.id,
        skill_ids=[sample_skill.id],
        tool_ids=[sample_tool.id],
        knowledge_pack_ids=[sample_knowledge_pack.id],
    )

    assert body["name"] == "my-bundle"
    assert ids(body["skills"]) == [sample_skill.id]
    assert ids(body["tools"]) == [sample_tool.id]
    assert ids(body["knowledge_packs"]) == [sample_knowledge_pack.id]


async def test_create_bundle_skips_items_inherited_from_agent(
    client, agent_profile_with_skill_and_tool, sample_skill, sample_tool
):
    body = await create_bundle(
        client,
        agent_profile_with_skill_and_tool.id,
        skill_ids=[sample_skill.id],
        tool_ids=[sample_tool.id],
    )

    assert body["skills"] == []
    assert body["tools"] == []


async def test_create_bundle_accepts_own_private_skill(
    client, sample_user, sample_agent_profile, make_skill
):
    private = await make_skill(owner=sample_user)

    body = await create_bundle(client, sample_agent_profile.id, skill_ids=[private.id])

    assert ids(body["skills"]) == [private.id]


async def test_create_bundle_rejects_foreign_private_skill(
    client, another_user, sample_agent_profile, make_skill
):
    foreign = await make_skill(owner=another_user)

    response = await client.post(
        "/config-bundles", json=create_payload(sample_agent_profile.id, skill_ids=[foreign.id])
    )

    assert response.status_code == 404, response.text


async def test_create_bundle_unknown_agent_returns_404(client):
    response = await client.post("/config-bundles", json=create_payload(999999))

    assert response.status_code == 404, response.text


async def test_create_bundle_unknown_skill_returns_404(client, sample_agent_profile):
    response = await client.post(
        "/config-bundles", json=create_payload(sample_agent_profile.id, skill_ids=[999999])
    )

    assert response.status_code == 404, response.text


async def test_create_bundle_unknown_tool_returns_404(client, sample_agent_profile):
    response = await client.post(
        "/config-bundles", json=create_payload(sample_agent_profile.id, tool_ids=[999999])
    )

    assert response.status_code == 404, response.text


async def test_create_bundle_unknown_pack_returns_404(client, sample_agent_profile):
    response = await client.post(
        "/config-bundles", json=create_payload(sample_agent_profile.id, knowledge_pack_ids=[999999])
    )

    assert response.status_code == 404, response.text


async def test_create_bundle_duplicate_name_returns_409(client, sample_agent_profile):
    await create_bundle(client, sample_agent_profile.id)

    response = await client.post("/config-bundles", json=create_payload(sample_agent_profile.id))

    assert response.status_code == 409, response.text


async def test_create_bundle_blank_name_is_rejected(client, sample_agent_profile):
    response = await client.post(
        "/config-bundles", json=create_payload(sample_agent_profile.id, name="   ")
    )

    assert response.status_code in (400, 422), response.text


async def test_create_from_agent_returns_bundle_for_agent(
    client, agent_profile_with_skill_and_tool
):
    response = await client.post(
        "/config-bundles/from-agent",
        json={"agent_id": agent_profile_with_skill_and_tool.id, "name": "from-agent", "description": "d"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "from-agent"
    assert body["agent_id"] == agent_profile_with_skill_and_tool.id


async def test_create_from_agent_exposes_agent_skills_and_tools_through_effective(
    client, agent_profile_with_skill_and_tool, sample_skill, sample_tool
):
    response = await client.post(
        "/config-bundles/from-agent",
        json={"agent_id": agent_profile_with_skill_and_tool.id, "name": "from-agent", "description": "d"},
    )
    assert response.status_code == 201, response.text

    effective = await client.get(f"/config-bundles/{response.json()['id']}/effective")

    assert effective.status_code == 200, effective.text
    body = effective.json()
    assert sample_skill.id in ids(body["skills"])
    assert sample_tool.id in ids(body["tools"])


async def test_create_from_agent_unknown_agent_returns_404(client):
    response = await client.post(
        "/config-bundles/from-agent", json={"agent_id": 999999, "name": "x", "description": "d"}
    )

    assert response.status_code == 404, response.text


async def test_create_from_agent_duplicate_name_returns_409(client, sample_agent_profile):
    payload = {"agent_id": sample_agent_profile.id, "name": "dup", "description": "d"}
    first = await client.post("/config-bundles/from-agent", json=payload)
    assert first.status_code == 201, first.text

    response = await client.post("/config-bundles/from-agent", json=payload)

    assert response.status_code == 409, response.text


async def test_list_bundles_returns_only_own(
    client, sample_user, another_user, make_agent, make_bundle
):
    agent = await make_agent()
    mine = await make_bundle(sample_user, agent)
    foreign = await make_bundle(another_user, agent)

    response = await client.get("/config-bundles")

    assert response.status_code == 200, response.text
    found = set(ids(response.json()))
    assert mine.id in found
    assert foreign.id not in found


async def test_list_bundles_filters_by_agent(client, sample_user, make_agent, make_bundle):
    first_agent = await make_agent()
    second_agent = await make_agent()
    first = await make_bundle(sample_user, first_agent)
    second = await make_bundle(sample_user, second_agent)

    response = await client.get("/config-bundles", params={"agent_id": first_agent.id})

    assert response.status_code == 200, response.text
    found = set(ids(response.json()))
    assert first.id in found
    assert second.id not in found


async def test_list_bundles_respects_limit(client, sample_user, make_agent, make_bundle):
    agent = await make_agent()
    await make_bundle(sample_user, agent)
    await make_bundle(sample_user, agent)

    response = await client.get("/config-bundles", params={"limit": 1})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
async def test_list_bundles_invalid_pagination_returns_422(client, params):
    response = await client.get("/config-bundles", params=params)

    assert response.status_code == 422, response.text


async def test_list_bundles_of_another_user_is_forbidden_for_regular_user(client, another_user):
    response = await client.get("/config-bundles", params={"user_id": another_user.id})

    assert response.status_code == 403, response.text


async def test_list_bundles_of_another_user_is_allowed_for_admin(
    client, as_admin, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.get("/config-bundles", params={"user_id": another_user.id})

    assert response.status_code == 200, response.text
    assert bundle.id in set(ids(response.json()))


async def test_get_bundle_returns_own_bundle(client, sample_user, make_agent, make_bundle):
    bundle = await make_bundle(sample_user, await make_agent())

    response = await client.get(f"/config-bundles/{bundle.id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == bundle.id


async def test_get_bundle_of_another_user_returns_404(
    client, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.get(f"/config-bundles/{bundle.id}")

    assert response.status_code == 404, response.text


async def test_get_unknown_bundle_returns_404(client):
    response = await client.get("/config-bundles/999999")

    assert response.status_code == 404, response.text


async def test_update_bundle_changes_name_and_description(
    client, sample_user, make_agent, make_bundle
):
    bundle = await make_bundle(sample_user, await make_agent())

    response = await client.patch(
        f"/config-bundles/{bundle.id}", json={"name": "renamed", "description": "new desc"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "renamed"
    assert response.json()["description"] == "new desc"


async def test_update_bundle_duplicate_name_returns_409(
    client, sample_user, make_agent, make_bundle
):
    agent = await make_agent()
    first = await make_bundle(sample_user, agent, name="first")
    await make_bundle(sample_user, agent, name="second")

    response = await client.patch(f"/config-bundles/{first.id}", json={"name": "second"})

    assert response.status_code == 409, response.text


async def test_update_bundle_keeping_own_name_is_allowed(
    client, sample_user, make_agent, make_bundle
):
    bundle = await make_bundle(sample_user, await make_agent(), name="same")

    response = await client.patch(f"/config-bundles/{bundle.id}", json={"name": "same"})

    assert response.status_code == 200, response.text


async def test_update_bundle_of_another_user_returns_404(
    client, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.patch(f"/config-bundles/{bundle.id}", json={"name": "hijack"})

    assert response.status_code == 404, response.text


async def test_delete_bundle_removes_it(client, sample_user, make_agent, make_bundle):
    bundle = await make_bundle(sample_user, await make_agent())

    response = await client.delete(f"/config-bundles/{bundle.id}")

    assert response.status_code == 204, response.text
    assert (await client.get(f"/config-bundles/{bundle.id}")).status_code == 404


async def test_delete_bundle_of_another_user_returns_404(
    client, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.delete(f"/config-bundles/{bundle.id}")

    assert response.status_code == 404, response.text


async def test_delete_unknown_bundle_returns_404(client):
    response = await client.delete("/config-bundles/999999")

    assert response.status_code == 404, response.text


async def test_clone_bundle_copies_items(
    client, sample_agent_profile, sample_skill, sample_tool, sample_knowledge_pack
):
    original = await create_bundle(
        client,
        sample_agent_profile.id,
        skill_ids=[sample_skill.id],
        tool_ids=[sample_tool.id],
        knowledge_pack_ids=[sample_knowledge_pack.id],
    )

    response = await client.post(
        f"/config-bundles/{original['id']}/clone", json={"name": "cloned", "description": "copy"}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] != original["id"]
    assert body["name"] == "cloned"
    assert ids(body["skills"]) == [sample_skill.id]
    assert ids(body["tools"]) == [sample_tool.id]
    assert ids(body["knowledge_packs"]) == [sample_knowledge_pack.id]


async def test_clone_bundle_duplicate_name_returns_409(
    client, sample_user, make_agent, make_bundle
):
    bundle = await make_bundle(sample_user, await make_agent(), name="taken")

    response = await client.post(
        f"/config-bundles/{bundle.id}/clone", json={"name": "taken", "description": "d"}
    )

    assert response.status_code == 409, response.text


async def test_clone_bundle_of_another_user_returns_404(
    client, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.post(
        f"/config-bundles/{bundle.id}/clone", json={"name": "stolen", "description": "d"}
    )

    assert response.status_code == 404, response.text


async def test_add_items_attaches_skill_tool_and_pack(
    client, sample_user, make_agent, make_bundle, sample_skill, sample_tool, sample_knowledge_pack
):
    bundle = await make_bundle(sample_user, await make_agent())

    response = await client.post(
        f"/config-bundles/{bundle.id}/items",
        json=items_payload(
            skill_ids=[sample_skill.id],
            tool_ids=[sample_tool.id],
            knowledge_pack_ids=[sample_knowledge_pack.id],
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert ids(body["skills"]) == [sample_skill.id]
    assert ids(body["tools"]) == [sample_tool.id]
    assert ids(body["knowledge_packs"]) == [sample_knowledge_pack.id]


async def test_add_items_twice_does_not_duplicate(
    client, sample_user, make_agent, make_bundle, sample_skill
):
    bundle = await make_bundle(sample_user, await make_agent())
    payload = items_payload(skill_ids=[sample_skill.id])

    await client.post(f"/config-bundles/{bundle.id}/items", json=payload)
    response = await client.post(f"/config-bundles/{bundle.id}/items", json=payload)

    assert response.status_code == 200, response.text
    assert ids(response.json()["skills"]) == [sample_skill.id]


async def test_add_items_unknown_skill_returns_404(client, sample_user, make_agent, make_bundle):
    bundle = await make_bundle(sample_user, await make_agent())

    response = await client.post(
        f"/config-bundles/{bundle.id}/items", json=items_payload(skill_ids=[999999])
    )

    assert response.status_code == 404, response.text


async def test_add_items_to_foreign_bundle_returns_404(
    client, another_user, make_agent, make_bundle, sample_skill
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.post(
        f"/config-bundles/{bundle.id}/items", json=items_payload(skill_ids=[sample_skill.id])
    )

    assert response.status_code == 404, response.text


async def test_remove_items_detaches_them(
    client, sample_agent_profile, sample_skill, sample_tool, sample_knowledge_pack
):
    bundle = await create_bundle(
        client,
        sample_agent_profile.id,
        skill_ids=[sample_skill.id],
        tool_ids=[sample_tool.id],
        knowledge_pack_ids=[sample_knowledge_pack.id],
    )

    response = await client.post(
        f"/config-bundles/{bundle['id']}/items/remove",
        json=items_payload(
            skill_ids=[sample_skill.id],
            tool_ids=[sample_tool.id],
            knowledge_pack_ids=[sample_knowledge_pack.id],
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skills"] == []
    assert body["tools"] == []
    assert body["knowledge_packs"] == []


async def test_remove_inherited_skill_returns_409(
    client, sample_user, agent_profile_with_skill_and_tool, make_bundle, sample_skill
):
    bundle = await make_bundle(sample_user, agent_profile_with_skill_and_tool)

    response = await client.post(
        f"/config-bundles/{bundle.id}/items/remove", json=items_payload(skill_ids=[sample_skill.id])
    )

    assert response.status_code == 409, response.text


async def test_remove_inherited_tool_returns_409(
    client, sample_user, agent_profile_with_skill_and_tool, make_bundle, sample_tool
):
    bundle = await make_bundle(sample_user, agent_profile_with_skill_and_tool)

    response = await client.post(
        f"/config-bundles/{bundle.id}/items/remove", json=items_payload(tool_ids=[sample_tool.id])
    )

    assert response.status_code == 409, response.text


async def test_remove_items_from_foreign_bundle_returns_404(
    client, another_user, make_agent, make_bundle, sample_skill
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.post(
        f"/config-bundles/{bundle.id}/items/remove", json=items_payload(skill_ids=[sample_skill.id])
    )

    assert response.status_code == 404, response.text


async def test_effective_bundle_merges_agent_and_bundle_items(
    client, sample_user, agent_profile_with_skill_and_tool, make_bundle, another_skill
):
    bundle = await create_bundle(
        client, agent_profile_with_skill_and_tool.id, skill_ids=[another_skill.id]
    )

    response = await client.get(f"/config-bundles/{bundle['id']}/effective")

    assert response.status_code == 200, response.text
    found = set(ids(response.json()["skills"]))
    assert another_skill.id in found
    assert agent_profile_with_skill_and_tool.skills[0].id in found


async def test_effective_bundle_of_another_user_returns_404(
    client, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.get(f"/config-bundles/{bundle.id}/effective")

    assert response.status_code == 404, response.text


async def test_effective_unknown_bundle_returns_404(client):
    response = await client.get("/config-bundles/999999/effective")

    assert response.status_code == 404, response.text


async def test_export_bundle_returns_zip_with_manifest_and_skill(
    client, sample_agent_profile, make_skill
):
    skill = await make_skill()
    bundle = await create_bundle(client, sample_agent_profile.id, skill_ids=[skill.id])

    response = await client.get(f"/config-bundles/{bundle['id']}/export")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert "agent.json" in names
    assert any(name.endswith("/SKILL.md") for name in names)
    manifest = json.loads(archive.read("agent.json").decode("utf-8"))
    assert manifest["bundle"]["id"] == bundle["id"]
    assert manifest["agent_profile"]["id"] == sample_agent_profile.id
    assert [entry["id"] for entry in manifest["skills"]] == [skill.id]
    assert response.headers["etag"] == f'"{manifest["version_hash"]}"'


async def test_export_bundle_is_deterministic(client, sample_agent_profile, make_skill):
    skill = await make_skill()
    bundle = await create_bundle(client, sample_agent_profile.id, skill_ids=[skill.id])

    first = await client.get(f"/config-bundles/{bundle['id']}/export")
    second = await client.get(f"/config-bundles/{bundle['id']}/export")

    assert first.content == second.content
    assert first.headers["etag"] == second.headers["etag"]


async def test_export_bundle_of_another_user_returns_404(
    client, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.get(f"/config-bundles/{bundle.id}/export")

    assert response.status_code == 404, response.text


async def test_export_unknown_bundle_returns_404(client):
    response = await client.get("/config-bundles/999999/export")

    assert response.status_code == 404, response.text