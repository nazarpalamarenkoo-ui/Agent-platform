from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.api.routers import config_bundles
from src.dependencies import get_config_bundle_service
from src.services.config_bundle_service import ConfigBundleService

pytestmark = pytest.mark.unit

ROUTER = config_bundles.router
SERVICE_DEPENDENCY = get_config_bundle_service
SERVICE_SPEC = ConfigBundleService

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)

CREATE_PAYLOAD = {
    "agent_id": 2,
    "name": "bundle",
    "description": "desc",
    "skill_ids": [1],
    "tool_ids": [2],
    "knowledge_pack_ids": [3],
}

FROM_AGENT_PAYLOAD = {"agent_id": 2, "name": "bundle", "description": "desc"}


def make_bundle(bundle_id=1, **overrides):
    data = {
        "id": bundle_id,
        "user_id": 7,
        "agent_id": 2,
        "name": f"bundle-{bundle_id}",
        "description": "Test bundle",
        "skills": [],
        "tools": [],
        "knowledge_packs": [],
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


async def test_create_bundle_returns_201(client, service):
    service.create_bundle.return_value = make_bundle(11)

    response = await client.post("/config-bundles", params={"user_id": 7}, json=CREATE_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["id"] == 11
    service.create_bundle.assert_awaited_once_with(7, 2, "bundle", "desc", [1], [2], [3])


async def test_create_bundle_value_error_returns_400(client, service):
    service.create_bundle.side_effect = ValueError("Tool with ID 2 does not exist")

    response = await client.post("/config-bundles", params={"user_id": 7}, json=CREATE_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Tool with ID 2 does not exist"


async def test_create_bundle_requires_user_id(client, service):
    response = await client.post("/config-bundles", json=CREATE_PAYLOAD)

    assert response.status_code == 422
    service.create_bundle.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**CREATE_PAYLOAD, "agent_id": "abc"},
        {**CREATE_PAYLOAD, "skill_ids": "abc"},
        {**CREATE_PAYLOAD, "knowledge_pack_ids": ["x"]},
    ],
)
async def test_create_bundle_rejects_invalid_payload(client, service, payload):
    response = await client.post("/config-bundles", params={"user_id": 7}, json=payload)

    assert response.status_code == 422
    service.create_bundle.assert_not_awaited()


async def test_create_from_agent_returns_201(client, service):
    service.create_from_agent.return_value = make_bundle(12)

    response = await client.post("/config-bundles/from-agent", params={"user_id": 7}, json=FROM_AGENT_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["id"] == 12
    service.create_from_agent.assert_awaited_once_with(7, 2, "bundle", "desc")


async def test_create_from_agent_value_error_returns_400(client, service):
    service.create_from_agent.side_effect = ValueError("Agent profile with ID 2 does not exist")

    response = await client.post("/config-bundles/from-agent", params={"user_id": 7}, json=FROM_AGENT_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Agent profile with ID 2 does not exist"


async def test_create_from_agent_requires_user_id(client, service):
    response = await client.post("/config-bundles/from-agent", json=FROM_AGENT_PAYLOAD)

    assert response.status_code == 422
    service.create_from_agent.assert_not_awaited()


async def test_clone_bundle_returns_201(client, service):
    service.clone_bundle.return_value = make_bundle(13)

    response = await client.post("/config-bundles/4/clone", params={"user_id": 7})

    assert response.status_code == 201
    assert response.json()["id"] == 13
    service.clone_bundle.assert_awaited_once_with(4, 7)


async def test_clone_bundle_value_error_returns_400(client, service):
    service.clone_bundle.side_effect = ValueError("Config bundle with ID 4 does not exist")

    response = await client.post("/config-bundles/4/clone", params={"user_id": 7})

    assert response.status_code == 400
    assert response.json()["detail"] == "Config bundle with ID 4 does not exist"


async def test_clone_bundle_requires_user_id(client, service):
    response = await client.post("/config-bundles/4/clone")

    assert response.status_code == 422
    service.clone_bundle.assert_not_awaited()


async def test_clone_bundle_invalid_id_returns_422(client, service):
    response = await client.post("/config-bundles/abc/clone", params={"user_id": 7})

    assert response.status_code == 422
    service.clone_bundle.assert_not_awaited()


async def test_get_user_bundles_returns_list(client, service):
    service.get_user_bundles.return_value = [make_bundle(1), make_bundle(2)]

    response = await client.get("/config-bundles", params={"user_id": 7, "agent_id": 2})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1, 2]
    service.get_user_bundles.assert_awaited_once_with(7, 2)


async def test_get_user_bundles_returns_empty_list(client, service):
    service.get_user_bundles.return_value = []

    response = await client.get("/config-bundles", params={"user_id": 7, "agent_id": 2})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("params", [{}, {"user_id": 7}, {"agent_id": 2}])
async def test_get_user_bundles_requires_both_query_params(client, service, params):
    response = await client.get("/config-bundles", params=params)

    assert response.status_code == 422
    service.get_user_bundles.assert_not_awaited()
