import pytest

from src.api.routers import knowledge_pack
from src.dependencies import get_knowledge_pack_service
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.services.knowledge_pack_service import KnowledgePackService

pytestmark = [pytest.mark.integration, pytest.mark.db, pytest.mark.usefixtures("default_actor")]


@pytest.fixture
def app(db_session, build_app):
    service = KnowledgePackService(
        KnowledgePackRepository(db_session),
        KnowledgeDomainRepository(db_session),
    )
    application = build_app(knowledge_pack.router)
    application.dependency_overrides[get_knowledge_pack_service] = lambda: service
    return application


def pack_payload(domain_id, **overrides):
    payload = {
        "name": "Fresh Pack",
        "domain_id": domain_id,
        "description": "Fresh reference material",
        "slug": "fresh-pack",
    }
    payload.update(overrides)
    return payload


async def ids_of(client, **params):
    response = await client.get("/knowledge-packs", params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


# --- create (admin only) ---


async def test_create_pack_as_regular_user_returns_403(client, sample_knowledge_domain):
    response = await client.post("/knowledge-packs", json=pack_payload(sample_knowledge_domain.id))

    assert response.status_code == 403, response.text


async def test_create_pack_returns_201(client, as_admin, sample_knowledge_domain):
    response = await client.post("/knowledge-packs", json=pack_payload(sample_knowledge_domain.id))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"]
    assert body["slug"] == "fresh-pack"


async def test_create_pack_unknown_domain_returns_400(client, as_admin):
    response = await client.post("/knowledge-packs", json=pack_payload(999999))

    assert response.status_code in (400, 404), response.text
    assert "999999" in response.json()["detail"]


async def test_create_pack_duplicate_name_in_same_domain_returns_400(
    client, as_admin, sample_knowledge_domain, sample_knowledge_pack
):
    payload = pack_payload(sample_knowledge_domain.id, name=sample_knowledge_pack.name)

    response = await client.post("/knowledge-packs", json=payload)

    assert response.status_code in (400, 409), response.text
    assert "already exists" in response.json()["detail"]


async def test_create_pack_duplicate_slug_returns_400(
    client, as_admin, sample_knowledge_domain, sample_knowledge_pack
):
    payload = pack_payload(sample_knowledge_domain.id, slug=sample_knowledge_pack.slug)

    response = await client.post("/knowledge-packs", json=payload)

    assert response.status_code in (400, 409), response.text
    assert "already exists" in response.json()["detail"]


async def test_create_pack_with_same_name_in_other_domain_returns_201(
    client, as_admin, another_knowledge_domain, sample_knowledge_pack
):
    payload = pack_payload(another_knowledge_domain.id, name=sample_knowledge_pack.name)

    response = await client.post("/knowledge-packs", json=payload)

    assert response.status_code == 201, response.text


# --- read ---


async def test_get_packs_returns_all_packs(client, sample_knowledge_pack, another_knowledge_pack):
    ids = await ids_of(client)

    assert {sample_knowledge_pack.id, another_knowledge_pack.id} <= ids


async def test_get_packs_respects_limit(client, sample_knowledge_pack, another_knowledge_pack):
    response = await client.get("/knowledge-packs", params={"limit": 1})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


async def test_get_packs_offset_beyond_total_returns_empty_list(client, sample_knowledge_pack):
    response = await client.get("/knowledge-packs", params={"offset": 1000})

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_get_pack_by_slug_returns_pack(client, sample_knowledge_pack):
    response = await client.get(f"/knowledge-packs/{sample_knowledge_pack.slug}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == sample_knowledge_pack.id
    assert body["slug"] == sample_knowledge_pack.slug


async def test_get_pack_by_slug_unknown_returns_404(client):
    response = await client.get("/knowledge-packs/does-not-exist")

    assert response.status_code == 404, response.text
    assert "does-not-exist" in response.json()["detail"]


async def test_get_packs_by_domain_returns_only_packs_of_that_domain(
    client, sample_knowledge_domain, sample_knowledge_pack, another_knowledge_pack
):
    response = await client.get(f"/knowledge-packs/by-domain/{sample_knowledge_domain.id}")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert sample_knowledge_pack.id in ids
    assert another_knowledge_pack.id not in ids


async def test_get_packs_by_domain_without_packs_returns_empty_list(client, another_knowledge_domain):
    response = await client.get(f"/knowledge-packs/by-domain/{another_knowledge_domain.id}")

    assert response.status_code == 200, response.text
    assert response.json() == []


# --- archive / restore (admin only) ---


async def test_archive_pack_as_regular_user_returns_403(client, sample_knowledge_pack):
    response = await client.post(f"/knowledge-packs/{sample_knowledge_pack.id}/archive")

    assert response.status_code == 403, response.text


async def test_restore_pack_as_regular_user_returns_403(client, sample_knowledge_pack):
    response = await client.post(f"/knowledge-packs/{sample_knowledge_pack.id}/restore")

    assert response.status_code == 403, response.text


async def test_archived_pack_is_hidden_unless_include_archived(client, as_admin, sample_knowledge_pack):
    response = await client.post(f"/knowledge-packs/{sample_knowledge_pack.id}/archive")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == sample_knowledge_pack.id
    assert sample_knowledge_pack.id not in await ids_of(client)
    assert sample_knowledge_pack.id in await ids_of(client, include_archived=True)


async def test_restore_pack_makes_it_visible_again(client, as_admin, sample_knowledge_pack):
    await client.post(f"/knowledge-packs/{sample_knowledge_pack.id}/archive")

    response = await client.post(f"/knowledge-packs/{sample_knowledge_pack.id}/restore")

    assert response.status_code == 200, response.text
    assert sample_knowledge_pack.id in await ids_of(client)


async def test_archive_unknown_pack_is_rejected(client, as_admin, assert_missing):
    assert_missing(await client.post("/knowledge-packs/999999/archive"))


async def test_restore_unknown_pack_is_rejected(client, as_admin, assert_missing):
    assert_missing(await client.post("/knowledge-packs/999999/restore"))