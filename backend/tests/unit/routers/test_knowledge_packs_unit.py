import pytest

from src.api.routers import knowledge_pack
from src.dependencies import get_knowledge_pack_service
from src.schemas.knowledge_pack import KnowledgePackRead
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.knowledge_pack_service import KnowledgePackService

pytestmark = pytest.mark.unit

ROUTER = knowledge_pack.router
SERVICE_DEPENDENCY = get_knowledge_pack_service
SERVICE_SPEC = KnowledgePackService

CREATE = {
    "name": "Backend API Design Pack",
    "domain_id": 1,
    "description": "Reference material",
    "slug": "backend-api-design-pack",
}
ERRORS = [
    (ValueError("bad"), 400),
    (NotFoundError("bad"), 404),
    (ConflictError("bad"), 409),
    (ForbiddenError("bad"), 403),
]


class TestListPacks:
    async def test_uses_default_pagination(self, client, service, actor, fake):
        service.list_packs.return_value = [fake(KnowledgePackRead, id=1), fake(KnowledgePackRead, id=2)]

        response = await client.get("/knowledge-packs")

        assert response.status_code == 200
        assert [p["id"] for p in response.json()] == [1, 2]
        service.list_packs.assert_awaited_once_with(
            actor, limit=100, offset=0, include_archived=False
        )

    async def test_passes_query_params(self, client, service, actor):
        service.list_packs.return_value = []

        response = await client.get(
            "/knowledge-packs", params={"limit": 5, "offset": 10, "include_archived": True}
        )

        assert response.status_code == 200
        service.list_packs.assert_awaited_once_with(
            actor, limit=5, offset=10, include_archived=True
        )

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}, {"limit": "x"}])
    async def test_rejects_invalid_pagination(self, client, service, params):
        response = await client.get("/knowledge-packs", params=params)

        assert response.status_code == 422
        service.list_packs.assert_not_awaited()

    async def test_forbidden_is_mapped_to_403(self, client, service):
        service.list_packs.side_effect = ForbiddenError("Admin access required")

        response = await client.get("/knowledge-packs", params={"include_archived": True})

        assert response.status_code == 403


class TestCreatePack:
    async def test_admin_creates_pack(self, client, service, admin, fake):
        service.create_pack.return_value = fake(KnowledgePackRead, id=4, slug=CREATE["slug"])

        response = await client.post("/knowledge-packs", json=CREATE)

        assert response.status_code == 201
        assert response.json()["id"] == 4
        service.create_pack.assert_awaited_once_with(
            admin, "Backend API Design Pack", 1, "Reference material", "backend-api-design-pack"
        )

    async def test_regular_user_gets_403(self, client, service):
        response = await client.post("/knowledge-packs", json=CREATE)

        assert response.status_code == 403
        assert service.mock_calls == []

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_service_errors(self, client, service, admin, error, code):
        service.create_pack.side_effect = error

        response = await client.post("/knowledge-packs", json=CREATE)

        assert response.status_code == code
        assert response.json()["detail"] == "bad"

    @pytest.mark.parametrize(
        "payload",
        [{}, {**CREATE, "domain_id": "abc"}, {**CREATE, "name": ["x"]}, {"name": "n"}],
    )
    async def test_rejects_invalid_payload(self, client, service, admin, payload):
        response = await client.post("/knowledge-packs", json=payload)

        assert response.status_code == 422
        service.create_pack.assert_not_awaited()


class TestGetPacks:
    async def test_by_domain_is_not_shadowed_by_slug_route(self, client, service, actor, fake):
        service.get_packs_by_domain.return_value = [fake(KnowledgePackRead, id=1)]

        response = await client.get("/knowledge-packs/by-domain/5", params={"limit": 3, "offset": 2})

        assert response.status_code == 200
        service.get_packs_by_domain.assert_awaited_once_with(actor, 5, limit=3, offset=2)
        service.get_pack_by_slug.assert_not_awaited()

    async def test_by_domain_invalid_id(self, client, service):
        response = await client.get("/knowledge-packs/by-domain/abc")

        assert response.status_code == 422
        service.get_packs_by_domain.assert_not_awaited()

    async def test_by_slug_returns_pack(self, client, service, actor, fake):
        service.get_pack_by_slug.return_value = fake(KnowledgePackRead, id=8, slug="my-pack")

        response = await client.get("/knowledge-packs/my-pack")

        assert response.status_code == 200
        assert response.json()["slug"] == "my-pack"
        service.get_pack_by_slug.assert_awaited_once_with(actor, "my-pack")

    async def test_by_slug_not_found(self, client, service):
        service.get_pack_by_slug.side_effect = NotFoundError("Pack with slug='x' not found")

        response = await client.get("/knowledge-packs/x")

        assert response.status_code == 404
        assert response.json()["detail"] == "Pack with slug='x' not found"


class TestArchiveAndRestore:
    @pytest.mark.parametrize("action,method", [("archive", "archive_pack"), ("restore", "restore_pack")])
    async def test_admin_can_call(self, client, service, admin, fake, action, method):
        getattr(service, method).return_value = fake(KnowledgePackRead, id=3)

        response = await client.post(f"/knowledge-packs/3/{action}")

        assert response.status_code == 200
        assert response.json()["id"] == 3
        getattr(service, method).assert_awaited_once_with(admin, 3)

    @pytest.mark.parametrize("action", ["archive", "restore"])
    async def test_regular_user_gets_403(self, client, service, action):
        response = await client.post(f"/knowledge-packs/3/{action}")

        assert response.status_code == 403
        assert service.mock_calls == []

    @pytest.mark.parametrize("action,method", [("archive", "archive_pack"), ("restore", "restore_pack")])
    async def test_not_found(self, client, service, admin, action, method):
        getattr(service, method).side_effect = NotFoundError("Pack 3 not found")

        response = await client.post(f"/knowledge-packs/3/{action}")

        assert response.status_code == 404

    async def test_invalid_id(self, client, service, admin):
        response = await client.post("/knowledge-packs/abc/archive")

        assert response.status_code == 422