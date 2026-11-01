from unittest.mock import create_autospec

import pytest

from src.api.routers import agents
from src.dependencies import get_agent_profile_service, get_config_bundle_service
from src.schemas.agent import AgentRead, CustomAgentRead
from src.services.agent_profile_service import AgentProfileService
from src.services.config_bundle_service import ConfigBundleService
from src.services.errors import ConflictError, ForbiddenError, NotFoundError

pytestmark = pytest.mark.unit

ROUTER = agents.router
SERVICE_DEPENDENCY = get_agent_profile_service
SERVICE_SPEC = AgentProfileService

CREATE = {"name": "agent", "description": "desc", "skill_ids": [1, 2], "tool_ids": [3]}
CUSTOM = {**CREATE, "knowledge_pack_ids": [4]}
ERRORS = [
    (ValueError("bad"), 400),
    (NotFoundError("bad"), 404),
    (ForbiddenError("bad"), 403),
    (ConflictError("bad"), 409),
]


@pytest.fixture
def bundle_service(override):
    return override(get_config_bundle_service, create_autospec(ConfigBundleService, instance=True))


class TestList:
    async def test_uses_defaults(self, client, service, actor, fake):
        service.list_profiles.return_value = [fake(AgentRead, id=1), fake(AgentRead, id=2)]

        response = await client.get("/agents")

        assert response.status_code == 200
        assert [a["id"] for a in response.json()] == [1, 2]
        service.list_profiles.assert_awaited_once_with(
            actor, limit=100, offset=0, include_archived=False
        )

    async def test_passes_query_params(self, client, service, actor):
        service.list_profiles.return_value = []

        await client.get("/agents", params={"limit": 10, "offset": 5, "include_archived": True})

        service.list_profiles.assert_awaited_once_with(
            actor, limit=10, offset=5, include_archived=True
        )

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}, {"limit": "x"}])
    async def test_rejects_invalid_pagination(self, client, service, params):
        response = await client.get("/agents", params=params)

        assert response.status_code == 422
        service.list_profiles.assert_not_awaited()

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, error, code):
        service.list_profiles.side_effect = error

        response = await client.get("/agents")

        assert response.status_code == code


class TestCreate:
    async def test_admin_creates_agent(self, client, service, as_admin, fake):
        service.create_profile.return_value = fake(AgentRead, id=5)

        response = await client.post("/agents", json=CREATE)

        assert response.status_code == 201
        assert response.json()["id"] == 5
        service.create_profile.assert_awaited_once_with(as_admin, "agent", "desc", [1, 2], [3])

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.post("/agents", json=CREATE)

        assert response.status_code == 403
        service.create_profile.assert_not_awaited()

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, as_admin, error, code):
        service.create_profile.side_effect = error

        response = await client.post("/agents", json=CREATE)

        assert response.status_code == code
        assert response.json()["detail"] == "bad"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {**CREATE, "name": ["x"]},
            {**CREATE, "skill_ids": "abc"},
            {**CREATE, "tool_ids": ["x"]},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, as_admin, payload):
        response = await client.post("/agents", json=payload)

        assert response.status_code == 422
        service.create_profile.assert_not_awaited()


class TestCreateCustom:
    async def test_any_user_creates_custom_agent(
        self, client, service, bundle_service, actor, fake
    ):
        bundle_service.create_custom_agent.return_value = fake(CustomAgentRead, id=8)

        response = await client.post("/agents/custom", json=CUSTOM)

        assert response.status_code == 201
        assert response.json()["id"] == 8
        bundle_service.create_custom_agent.assert_awaited_once_with(
            actor.id, "agent", "desc", [1, 2], [3], [4]
        )
        service.create_profile.assert_not_awaited()

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, bundle_service, error, code):
        bundle_service.create_custom_agent.side_effect = error

        response = await client.post("/agents/custom", json=CUSTOM)

        assert response.status_code == code

    @pytest.mark.parametrize(
        "payload", [{}, {**CUSTOM, "knowledge_pack_ids": ["x"]}, {**CUSTOM, "name": ["x"]}]
    )
    async def test_rejects_invalid_payload(self, client, service, bundle_service, payload):
        response = await client.post("/agents/custom", json=payload)

        assert response.status_code == 422
        bundle_service.create_custom_agent.assert_not_awaited()


class TestGet:
    async def test_returns_agent(self, client, service, actor, fake):
        service.get_profile.return_value = fake(AgentRead, id=7)

        response = await client.get("/agents/7")

        assert response.status_code == 200
        assert response.json()["id"] == 7
        service.get_profile.assert_awaited_once_with(actor, 7)

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, error, code):
        service.get_profile.side_effect = error

        response = await client.get("/agents/7")

        assert response.status_code == code

    async def test_invalid_id(self, client, service):
        response = await client.get("/agents/abc")

        assert response.status_code == 422
        service.get_profile.assert_not_awaited()


class TestUpdate:
    async def test_admin_updates_agent(self, client, service, as_admin, fake):
        service.update_profile.return_value = fake(AgentRead, id=3)

        response = await client.put(
            "/agents/3", json={"description": "new", "skill_ids": [1], "tool_ids": [2]}
        )

        assert response.status_code == 200
        service.update_profile.assert_awaited_once_with(
            as_admin, 3, description="new", skill_ids=[1], tool_ids=[2]
        )

    async def test_partial_update_passes_none(self, client, service, as_admin, fake):
        service.update_profile.return_value = fake(AgentRead, id=3)

        await client.put("/agents/3", json={"description": "new"})

        service.update_profile.assert_awaited_once_with(
            as_admin, 3, description="new", skill_ids=None, tool_ids=None
        )

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.put("/agents/3", json={"description": "x"})

        assert response.status_code == 403
        service.update_profile.assert_not_awaited()

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, as_admin, error, code):
        service.update_profile.side_effect = error

        response = await client.put("/agents/3", json={"description": "x"})

        assert response.status_code == code


@pytest.mark.parametrize("action,method", [("archive", "archive_profile"), ("restore", "restore_profile")])
class TestArchiveRestore:
    async def test_admin_can_call(self, client, service, as_admin, fake, action, method):
        getattr(service, method).return_value = fake(AgentRead, id=3)

        response = await client.post(f"/agents/3/{action}")

        assert response.status_code == 200
        getattr(service, method).assert_awaited_once_with(as_admin, 3)

    async def test_regular_user_is_forbidden(self, client, service, action, method):
        response = await client.post(f"/agents/3/{action}")

        assert response.status_code == 403
        getattr(service, method).assert_not_awaited()

    async def test_not_found(self, client, service, as_admin, action, method):
        getattr(service, method).side_effect = NotFoundError("nf")

        response = await client.post(f"/agents/3/{action}")

        assert response.status_code == 404