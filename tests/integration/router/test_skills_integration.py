import pytest

from src.api.routers import skills
from src.dependencies import get_skill_service
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.skill_repo import SkillRepository
from src.services.skill_service import SkillService

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    service = SkillService(SkillRepository(db_session), KnowledgeDomainRepository(db_session))
    application = build_app(skills.router)
    application.dependency_overrides[get_skill_service] = lambda: service
    return application


async def test_create_skill_without_domains_returns_201(client):
    payload = {"skill_name": "code-review", "description": "Review code", "domain_ids": []}

    response = await client.post("/skills", json=payload)

    assert response.status_code == 201
    assert response.json()["id"]


async def test_create_skill_with_domains_is_listed_by_each_domain(
    client, sample_knowledge_domain, another_knowledge_domain
):
    payload = {
        "skill_name": "code-review",
        "description": "Review code",
        "domain_ids": [sample_knowledge_domain.id, another_knowledge_domain.id],
    }

    created = await client.post("/skills", json=payload)
    skill_id = created.json()["id"]

    assert created.status_code == 201
    for domain in (sample_knowledge_domain, another_knowledge_domain):
        response = await client.get(f"/skills/by-domain/{domain.id}")
        assert response.status_code == 200
        assert skill_id in {item["id"] for item in response.json()}


async def test_create_skill_duplicate_name_returns_400(client, sample_skill):
    payload = {"skill_name": sample_skill.skill_name, "description": "Other", "domain_ids": []}

    response = await client.post("/skills", json=payload)

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


async def test_create_skill_with_unknown_domain_returns_400(client):
    payload = {"skill_name": "code-review", "description": "Review code", "domain_ids": [999999]}

    response = await client.post("/skills", json=payload)

    assert response.status_code == 400
    assert "999999" in response.json()["detail"]


async def test_get_skills_returns_all_skills(client, sample_skill, another_skill):
    response = await client.get("/skills")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert {sample_skill.id, another_skill.id} <= ids


async def test_get_skills_respects_limit(client, sample_skill, another_skill):
    response = await client.get("/skills", params={"limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_get_skills_offset_beyond_total_returns_empty_list(client, sample_skill):
    response = await client.get("/skills", params={"offset": 1000})

    assert response.status_code == 200
    assert response.json() == []


async def test_get_skill_returns_existing_skill(client, sample_skill):
    response = await client.get(f"/skills/{sample_skill.id}")

    assert response.status_code == 200
    assert response.json()["id"] == sample_skill.id


async def test_get_skill_unknown_id_returns_400(client):
    response = await client.get("/skills/999999")

    assert response.status_code == 400
    assert "999999" in response.json()["detail"]


async def test_get_skills_by_domain_returns_only_skills_of_that_domain(
    client, skill_with_domain, another_skill, sample_knowledge_domain
):
    response = await client.get(f"/skills/by-domain/{sample_knowledge_domain.id}")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert skill_with_domain.id in ids
    assert another_skill.id not in ids


async def test_get_skills_by_domain_without_skills_returns_empty_list(client, another_knowledge_domain):
    response = await client.get(f"/skills/by-domain/{another_knowledge_domain.id}")

    assert response.status_code == 200
    assert response.json() == []
