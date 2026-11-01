import pytest

from src.api.routers import domains
from src.db.models.knowledge_domains import KnowledgeDomain
from src.dependencies import get_domain_service
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.services.domain_service import DomainService

pytestmark = [pytest.mark.integration, pytest.mark.db, pytest.mark.usefixtures("default_actor")]


@pytest.fixture
def app(db_session, build_app):
    service = DomainService(KnowledgeDomainRepository(db_session))
    application = build_app(domains.router)
    application.dependency_overrides[get_domain_service] = lambda: service
    return application


def domain_payload(**overrides):
    payload = {
        "slug": "data-engineering",
        "name": "Data Engineering",
        "description": "Pipelines and warehouses",
        "parent_domain_id": None,
    }
    payload.update(overrides)
    return payload


async def test_create_domain_as_regular_user_returns_403(client):
    response = await client.post("/domains", json=domain_payload())

    assert response.status_code == 403, response.text


async def test_create_root_domain_returns_201(client, as_admin):
    response = await client.post("/domains", json=domain_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"]
    assert body["slug"] == "data-engineering"


async def test_create_child_domain_returns_201(client, as_admin, sample_knowledge_domain):
    payload = domain_payload(slug="graphql-design", parent_domain_id=sample_knowledge_domain.id)

    response = await client.post("/domains", json=payload)

    assert response.status_code == 201, response.text
    assert response.json()["slug"] == "graphql-design"


async def test_create_domain_duplicate_slug_returns_400(client, as_admin, sample_knowledge_domain):
    response = await client.post("/domains", json=domain_payload(slug=sample_knowledge_domain.slug))

    assert response.status_code == 400, response.text
    assert "already exists" in response.json()["detail"]


async def test_create_domain_with_unknown_parent_returns_400(client, as_admin):
    response = await client.post("/domains", json=domain_payload(parent_domain_id=999999))

    assert response.status_code == 400, response.text
    assert "999999" in response.json()["detail"]


async def test_get_created_domain_by_id_returns_domain(client, as_admin, db_session):
    created = await client.post("/domains", json=domain_payload())
    assert created.status_code == 201, created.text
    domain = await db_session.get(KnowledgeDomain, created.json()["id"])
    await db_session.refresh(domain, attribute_names=["children"])

    response = await client.get(f"/domains/{created.json()['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["slug"] == "data-engineering"


async def test_get_domain_available_for_regular_user(client, sample_knowledge_domain):
    response = await client.get(f"/domains/{sample_knowledge_domain.id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == sample_knowledge_domain.id


async def test_get_domain_unknown_id_returns_404(client):
    response = await client.get("/domains/999999")

    assert response.status_code == 404, response.text
    assert "999999" in response.json()["detail"]


async def test_get_all_domains_returns_all_domains(client, sample_knowledge_domain, another_knowledge_domain):
    response = await client.get("/domains")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert {sample_knowledge_domain.id, another_knowledge_domain.id} <= ids


async def test_get_all_domains_respects_limit(client, sample_knowledge_domain, another_knowledge_domain):
    response = await client.get("/domains", params={"limit": 1})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
async def test_get_all_domains_invalid_pagination_returns_422(client, params):
    response = await client.get("/domains", params=params)

    assert response.status_code == 422, response.text


async def test_get_root_domains_excludes_child_domains(
    client, sample_knowledge_domain, another_knowledge_domain, child_knowledge_domain
):
    response = await client.get("/domains/roots")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert {sample_knowledge_domain.id, another_knowledge_domain.id} <= ids
    assert child_knowledge_domain.id not in ids