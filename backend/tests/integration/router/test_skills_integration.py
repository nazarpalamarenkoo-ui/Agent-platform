import pytest

from src.api.routers import skills
from src.dependencies import get_skill_service
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.notification_repo import NotificationRepository
from src.repositories.skill_repo import SkillRepository
from src.services.skill_service import SkillService

pytestmark = [pytest.mark.integration, pytest.mark.db, pytest.mark.usefixtures("default_actor")]


@pytest.fixture
def app(db_session, build_app):
    service = SkillService(
        SkillRepository(db_session),
        KnowledgeDomainRepository(db_session),
        ConfigBundleRepository(db_session),
        NotificationRepository(db_session),
    )
    application = build_app(skills.router)
    application.dependency_overrides[get_skill_service] = lambda: service
    return application


def skill_payload(**overrides):
    payload = {
        "skill_name": "code-review",
        "description": "Review code",
        "content": "Check naming, tests and error handling.",
        "domain_ids": [],
    }
    payload.update(overrides)
    return payload


async def ids_of(client, url="/skills", **params):
    response = await client.get(url, params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


async def test_create_skill_as_regular_user_returns_403(client):
    response = await client.post("/skills", json=skill_payload())

    assert response.status_code == 403, response.text


async def test_create_skill_without_domains_returns_201(client, as_admin):
    response = await client.post("/skills", json=skill_payload())

    assert response.status_code == 201, response.text
    assert response.json()["id"]


async def test_create_skill_with_domains_is_listed_by_each_domain(
    client, as_admin, sample_knowledge_domain, another_knowledge_domain
):
    payload = skill_payload(domain_ids=[sample_knowledge_domain.id, another_knowledge_domain.id])

    created = await client.post("/skills", json=payload)
    assert created.status_code == 201, created.text

    for domain in (sample_knowledge_domain, another_knowledge_domain):
        assert created.json()["id"] in await ids_of(client, f"/skills/by-domain/{domain.id}")


async def test_create_skill_duplicate_name_returns_400(client, as_admin, sample_skill):
    response = await client.post("/skills", json=skill_payload(skill_name=sample_skill.skill_name))

    assert response.status_code in (400, 409), response.text
    assert "already exists" in response.json()["detail"]


async def test_create_skill_with_unknown_domain_returns_400(client, as_admin):
    response = await client.post("/skills", json=skill_payload(domain_ids=[999999]))

    assert response.status_code in (400, 404), response.text
    assert "999999" in response.json()["detail"]


# --- read ---


async def test_get_skills_returns_all_skills(client, sample_skill, another_skill):
    ids = await ids_of(client)

    assert {sample_skill.id, another_skill.id} <= ids


async def test_get_skills_respects_limit(client, sample_skill, another_skill):
    response = await client.get("/skills", params={"limit": 1})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


async def test_get_skills_offset_beyond_total_returns_empty_list(client, sample_skill):
    response = await client.get("/skills", params={"offset": 1000})

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_get_skills_filters_by_domain_query_param(
    client, skill_with_domain, another_skill, sample_knowledge_domain
):
    ids = await ids_of(client, domain_id=sample_knowledge_domain.id)

    assert skill_with_domain.id in ids
    assert another_skill.id not in ids


async def test_get_skill_returns_existing_skill(client, sample_skill):
    response = await client.get(f"/skills/{sample_skill.id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == sample_skill.id


async def test_get_unknown_skill_is_rejected(client, assert_missing):
    assert_missing(await client.get("/skills/999999"))


async def test_get_skills_by_domain_returns_only_skills_of_that_domain(
    client, skill_with_domain, another_skill, sample_knowledge_domain
):
    ids = await ids_of(client, f"/skills/by-domain/{sample_knowledge_domain.id}")

    assert skill_with_domain.id in ids
    assert another_skill.id not in ids


async def test_get_skills_by_domain_without_skills_returns_empty_list(client, another_knowledge_domain):
    response = await client.get(f"/skills/by-domain/{another_knowledge_domain.id}")

    assert response.status_code == 200, response.text
    assert response.json() == []


# --- download ---


async def test_download_skill_returns_markdown_attachment(client, sample_skill):
    response = await client.get(f"/skills/{sample_skill.id}/download")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="SKILL.md"'
    assert sample_skill.skill_name in response.text


async def test_download_unknown_skill_is_rejected(client, assert_missing):
    assert_missing(await client.get("/skills/999999/download"))


# --- update (admin only) ---


async def test_update_skill_as_regular_user_returns_403(client, sample_skill):
    response = await client.put(f"/skills/{sample_skill.id}", json={"description": "Changed"})

    assert response.status_code == 403, response.text


async def test_update_skill_changes_description_and_content(client, as_admin, sample_skill):
    response = await client.put(
        f"/skills/{sample_skill.id}", json={"description": "Changed", "content": "New content"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["description"] == "Changed"
    fetched = await client.get(f"/skills/{sample_skill.id}")
    assert fetched.json()["description"] == "Changed"


async def test_update_unknown_skill_is_rejected(client, as_admin, assert_missing):
    assert_missing(await client.put("/skills/999999", json={"description": "Changed"}))


# --- archive / restore (admin only) ---


async def test_archive_skill_as_regular_user_returns_403(client, sample_skill):
    response = await client.post(f"/skills/{sample_skill.id}/archive")

    assert response.status_code == 403, response.text


async def test_restore_skill_as_regular_user_returns_403(client, sample_skill):
    response = await client.post(f"/skills/{sample_skill.id}/restore")

    assert response.status_code == 403, response.text


async def test_archived_skill_is_hidden_unless_include_archived(client, as_admin, sample_skill):
    response = await client.post(f"/skills/{sample_skill.id}/archive")

    assert response.status_code == 200, response.text
    assert sample_skill.id not in await ids_of(client)
    assert sample_skill.id in await ids_of(client, include_archived=True)


async def test_restore_skill_makes_it_visible_again(client, as_admin, sample_skill):
    await client.post(f"/skills/{sample_skill.id}/archive")

    response = await client.post(f"/skills/{sample_skill.id}/restore")

    assert response.status_code == 200, response.text
    assert sample_skill.id in await ids_of(client)


async def test_archive_unknown_skill_is_rejected(client, as_admin, assert_missing):
    assert_missing(await client.post("/skills/999999/archive"))