import pytest

from src.api.routers import knowledge_pack
from src.dependencies import get_knowledge_pack_service
from src.services.knowledge_pack_service import KnowledgePackService
from src.schemas.knowledge_pack import KnowledgePackRead

pytestmark = pytest.mark.unit

ROUTER = knowledge_pack.router
SERVICE_DEPENDENCY = get_knowledge_pack_service
SERVICE_SPEC = KnowledgePackService

VALID_PAYLOAD = {
    "name": "Backend API Design Pack",
    "domain_id": 1,
    "description": "Reference material",
    "slug": "backend-api-design-pack",
}


async def test_create_pack_returns_201(client, service, fake):
    service.create_pack.return_value = fake(KnowledgePackRead, id=4, slug="backend-api-design-pack")

    response = await client.post("/knowledge-packs", json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 4
    assert body["slug"] == "backend-api-design-pack"
    service.create_pack.assert_awaited_once_with(
        "Backend API Design Pack", 1, "Reference material", "backend-api-design-pack"
    )


async def test_create_pack_value_error_returns_400(client, service):
    service.create_pack.side_effect = ValueError("Domain with id=1 does not exist")

    response = await client.post("/knowledge-packs", json=VALID_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Domain with id=1 does not exist"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**VALID_PAYLOAD, "domain_id": "abc"},
        {**VALID_PAYLOAD, "name": ["x"]},
    ],
)
async def test_create_pack_rejects_invalid_payload(client, service, payload):
    response = await client.post("/knowledge-packs", json=payload)

    assert response.status_code == 422
    service.create_pack.assert_not_awaited()


async def test_get_packs_by_domain_returns_list(client, service, fake):
    service.get_packs_by_domain.return_value = [fake(KnowledgePackRead, id=1), fake(KnowledgePackRead, id=2)]

    response = await client.get("/knowledge-packs/by-domain/5")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1, 2]
    service.get_packs_by_domain.assert_awaited_once_with(5)
    service.get_pack_by_slug.assert_not_awaited()


async def test_get_packs_by_domain_returns_empty_list(client, service):
    service.get_packs_by_domain.return_value = []

    response = await client.get("/knowledge-packs/by-domain/5")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_packs_by_domain_invalid_id_returns_422(client, service):
    response = await client.get("/knowledge-packs/by-domain/abc")

    assert response.status_code == 422
    service.get_packs_by_domain.assert_not_awaited()


async def test_get_pack_by_slug_returns_pack(client, service, fake):
    service.get_pack_by_slug.return_value = fake(KnowledgePackRead, id=8, slug="my-pack")

    response = await client.get("/knowledge-packs/my-pack")

    assert response.status_code == 200
    assert response.json()["slug"] == "my-pack"
    service.get_pack_by_slug.assert_awaited_once_with("my-pack")


async def test_get_pack_by_slug_not_found_returns_404(client, service):
    service.get_pack_by_slug.side_effect = ValueError("Pack with slug='my-pack' not found")

    response = await client.get("/knowledge-packs/my-pack")

    assert response.status_code == 404
    assert response.json()["detail"] == "Pack with slug='my-pack' not found"