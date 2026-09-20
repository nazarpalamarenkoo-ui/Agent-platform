import pytest

from src.api.routers import skills
from src.dependencies import get_skill_service
from src.services.skill_service import SkillService
from src.schemas.skill import SkillRead

pytestmark = pytest.mark.unit

ROUTER = skills.router
SERVICE_DEPENDENCY = get_skill_service
SERVICE_SPEC = SkillService

VALID_PAYLOAD = {
    "skill_name": "summarization",
    "description": "Summarize text",
    "domain_ids": [1, 2],
}


async def test_create_skill_returns_201(client, service, fake):
    service.create_skill.return_value = fake(SkillRead, id=5)

    response = await client.post("/skills", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["id"] == 5
    service.create_skill.assert_awaited_once_with("summarization", "Summarize text", [1, 2])


async def test_create_skill_value_error_returns_400(client, service):
    service.create_skill.side_effect = ValueError("Skill 'summarization' already exists")

    response = await client.post("/skills", json=VALID_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Skill 'summarization' already exists"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**VALID_PAYLOAD, "skill_name": ["x"]},
        {**VALID_PAYLOAD, "domain_ids": "abc"},
        {**VALID_PAYLOAD, "domain_ids": ["x"]},
    ],
)
async def test_create_skill_rejects_invalid_payload(client, service, payload):
    response = await client.post("/skills", json=payload)

    assert response.status_code == 422
    service.create_skill.assert_not_awaited()


async def test_get_skills_uses_default_pagination(client, service, fake):
    service.get_all_skills.return_value = [fake(SkillRead, id=1), fake(SkillRead, id=2)]

    response = await client.get("/skills")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1, 2]
    service.get_all_skills.assert_awaited_once_with(100, 0)


async def test_get_skills_passes_custom_pagination(client, service):
    service.get_all_skills.return_value = []

    response = await client.get("/skills", params={"limit": 3, "offset": 6})

    assert response.status_code == 200
    service.get_all_skills.assert_awaited_once_with(3, 6)


async def test_get_skills_value_error_returns_400(client, service):
    service.get_all_skills.side_effect = ValueError("bad pagination")

    response = await client.get("/skills")

    assert response.status_code == 400
    assert response.json()["detail"] == "bad pagination"


@pytest.mark.parametrize("params", [{"limit": "abc"}, {"offset": "abc"}])
async def test_get_skills_rejects_invalid_pagination(client, service, params):
    response = await client.get("/skills", params=params)

    assert response.status_code == 422
    service.get_all_skills.assert_not_awaited()


async def test_get_skill_returns_skill(client, service, fake):
    service.get_skill.return_value = fake(SkillRead, id=9)

    response = await client.get("/skills/9")

    assert response.status_code == 200
    assert response.json()["id"] == 9
    service.get_skill.assert_awaited_once_with(9)


async def test_get_skill_value_error_returns_400(client, service):
    service.get_skill.side_effect = ValueError("Skill 9 not found")

    response = await client.get("/skills/9")

    assert response.status_code == 400
    assert response.json()["detail"] == "Skill 9 not found"


async def test_get_skill_invalid_id_returns_422(client, service):
    response = await client.get("/skills/abc")

    assert response.status_code == 422
    service.get_skill.assert_not_awaited()


async def test_get_skills_by_domain_returns_list(client, service, fake):
    service.get_skills_by_domain.return_value = [fake(SkillRead, id=1)]

    response = await client.get("/skills/by-domain/4")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1]
    service.get_skills_by_domain.assert_awaited_once_with(4)
    service.get_skill.assert_not_awaited()


async def test_get_skills_by_domain_value_error_returns_400(client, service):
    service.get_skills_by_domain.side_effect = ValueError("Domain 4 not found")

    response = await client.get("/skills/by-domain/4")

    assert response.status_code == 400
    assert response.json()["detail"] == "Domain 4 not found"


async def test_get_skills_by_domain_invalid_id_returns_422(client, service):
    response = await client.get("/skills/by-domain/abc")

    assert response.status_code == 422
    service.get_skills_by_domain.assert_not_awaited()