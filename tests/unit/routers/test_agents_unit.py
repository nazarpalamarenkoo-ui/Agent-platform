from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.api.routers import agents
from src.dependencies import get_agent_profile_service
from src.services.agent_profile_service import AgentProfileService

pytestmark = pytest.mark.unit

ROUTER = agents.router
SERVICE_DEPENDENCY = get_agent_profile_service
SERVICE_SPEC = AgentProfileService

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)

VALID_PAYLOAD = {
    "name": "agent",
    "description": "desc",
    "skill_ids": [1, 2],
    "tool_ids": [3],
}


def make_agent(agent_id=1, **overrides):
    data = {
        "id": agent_id,
        "agent_name": f"agent-{agent_id}",
        "name": f"agent-{agent_id}",
        "description": "Test agent",
        "skills": [],
        "tools": [],
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


async def test_create_agent_returns_201(client, service):
    service.create_profile.return_value = make_agent(5)

    response = await client.post("/agents", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["id"] == 5
    service.create_profile.assert_awaited_once_with("agent", "desc", [1, 2], [3])


async def test_create_agent_value_error_returns_400(client, service):
    service.create_profile.side_effect = ValueError("Skill 99 not found")

    response = await client.post("/agents", json=VALID_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Skill 99 not found"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**VALID_PAYLOAD, "name": ["not", "a", "string"]},
        {**VALID_PAYLOAD, "skill_ids": "abc"},
        {**VALID_PAYLOAD, "tool_ids": ["x"]},
    ],
)
async def test_create_agent_rejects_invalid_payload(client, service, payload):
    response = await client.post("/agents", json=payload)

    assert response.status_code == 422
    service.create_profile.assert_not_awaited()


async def test_create_agent_without_body_returns_422(client, service):
    response = await client.post("/agents")

    assert response.status_code == 422
    service.create_profile.assert_not_awaited()


async def test_get_agents_uses_default_pagination(client, service):
    service.get_all_profiles.return_value = [make_agent(1), make_agent(2)]

    response = await client.get("/agents")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1, 2]
    service.get_all_profiles.assert_awaited_once_with(limit=100, offset=0)


async def test_get_agents_passes_custom_pagination(client, service):
    service.get_all_profiles.return_value = []

    response = await client.get("/agents", params={"limit": 10, "offset": 5})

    assert response.status_code == 200
    assert response.json() == []
    service.get_all_profiles.assert_awaited_once_with(limit=10, offset=5)


@pytest.mark.parametrize("params", [{"limit": "abc"}, {"offset": "abc"}])
async def test_get_agents_rejects_invalid_pagination(client, service, params):
    response = await client.get("/agents", params=params)

    assert response.status_code == 422
    service.get_all_profiles.assert_not_awaited()


async def test_get_agent_returns_agent(client, service):
    service.get_profile.return_value = make_agent(7)

    response = await client.get("/agents/7")

    assert response.status_code == 200
    assert response.json()["id"] == 7
    service.get_profile.assert_awaited_once_with(7)


async def test_get_agent_not_found_returns_404(client, service):
    service.get_profile.side_effect = ValueError("Agent profile 7 not found")

    response = await client.get("/agents/7")

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent profile 7 not found"


async def test_get_agent_invalid_id_returns_422(client, service):
    response = await client.get("/agents/abc")

    assert response.status_code == 422
    service.get_profile.assert_not_awaited()
