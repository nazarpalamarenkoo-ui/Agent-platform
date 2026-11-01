import pytest

from src.api.routers import skills
from src.dependencies import get_skill_service
from src.schemas.skill import SkillRead
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.skill_service import SkillService

pytestmark = pytest.mark.unit

ROUTER = skills.router
SERVICE_DEPENDENCY = get_skill_service
SERVICE_SPEC = SkillService

VALID_PAYLOAD = {
    "skill_name": "summarization",
    "description": "Summarize text",
    "content": "# Body",
    "domain_ids": [1, 2],
}

ERRORS = [
    (NotFoundError("nf"), 404),
    (ForbiddenError("fb"), 403),
    (ConflictError("cf"), 409),
    (ValueError("bad"), 400),
]


class TestList:
    async def test_uses_defaults(self, client, service, actor, fake):
        service.list_skills.return_value = [fake(SkillRead, id=1), fake(SkillRead, id=2)]

        response = await client.get("/skills")

        assert response.status_code == 200
        assert [s["id"] for s in response.json()] == [1, 2]
        service.list_skills.assert_awaited_once_with(
            actor, limit=100, offset=0, domain_id=None, include_archived=False
        )

    async def test_passes_filters(self, client, service, actor):
        service.list_skills.return_value = []

        await client.get(
            "/skills", params={"limit": 3, "offset": 6, "domain_id": 4, "include_archived": True}
        )

        service.list_skills.assert_awaited_once_with(
            actor, limit=3, offset=6, domain_id=4, include_archived=True
        )

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}, {"domain_id": "x"}])
    async def test_rejects_invalid_params(self, client, service, params):
        response = await client.get("/skills", params=params)

        assert response.status_code == 422
        service.list_skills.assert_not_awaited()

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, error, code):
        service.list_skills.side_effect = error

        response = await client.get("/skills", params={"include_archived": True})

        assert response.status_code == code

    async def test_by_domain_route_is_not_shadowed_by_skill_id(self, client, service, actor, fake):
        service.list_skills.return_value = [fake(SkillRead, id=1)]

        response = await client.get("/skills/by-domain/4", params={"limit": 5})

        assert response.status_code == 200
        service.list_skills.assert_awaited_once_with(actor, limit=5, offset=0, domain_id=4)
        service.get_skill.assert_not_awaited()


class TestCreate:
    async def test_admin_creates_skill(self, client, service, as_admin, fake):
        service.create_global_skill.return_value = fake(SkillRead, id=5)

        response = await client.post("/skills", json=VALID_PAYLOAD)

        assert response.status_code == 201
        assert response.json()["id"] == 5
        service.create_global_skill.assert_awaited_once_with(
            as_admin, "summarization", "Summarize text", "# Body", [1, 2]
        )

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.post("/skills", json=VALID_PAYLOAD)

        assert response.status_code == 403
        service.create_global_skill.assert_not_awaited()

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, as_admin, error, code):
        service.create_global_skill.side_effect = error

        response = await client.post("/skills", json=VALID_PAYLOAD)

        assert response.status_code == code
        assert response.json()["detail"] == str(error)

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {k: v for k, v in VALID_PAYLOAD.items() if k != "content"},
            {**VALID_PAYLOAD, "skill_name": ["x"]},
            {**VALID_PAYLOAD, "domain_ids": ["x"]},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, as_admin, payload):
        response = await client.post("/skills", json=payload)

        assert response.status_code == 422
        service.create_global_skill.assert_not_awaited()


class TestGet:
    async def test_returns_skill(self, client, service, actor, fake):
        service.get_skill.return_value = fake(SkillRead, id=9)

        response = await client.get("/skills/9")

        assert response.status_code == 200
        assert response.json()["id"] == 9
        service.get_skill.assert_awaited_once_with(actor, 9)

    async def test_not_found_returns_404(self, client, service):
        service.get_skill.side_effect = NotFoundError("Skill not found")

        response = await client.get("/skills/9")

        assert response.status_code == 404

    async def test_invalid_id_returns_422(self, client, service):
        response = await client.get("/skills/abc")

        assert response.status_code == 422
        service.get_skill.assert_not_awaited()


class TestDownload:
    async def test_returns_markdown_attachment(self, client, service, actor):
        service.export_skill_md.return_value = "---\nname: x\n---\nbody"

        response = await client.get("/skills/9/download")

        assert response.status_code == 200
        assert response.text == "---\nname: x\n---\nbody"
        assert response.headers["content-type"].startswith("text/markdown")
        assert response.headers["content-disposition"] == 'attachment; filename="SKILL.md"'
        service.export_skill_md.assert_awaited_once_with(actor, 9)

    async def test_not_found_returns_404(self, client, service):
        service.export_skill_md.side_effect = NotFoundError("Skill not found")

        response = await client.get("/skills/9/download")

        assert response.status_code == 404


class TestUpdate:
    async def test_admin_updates_skill(self, client, service, as_admin, fake):
        service.update_global_skill.return_value = fake(SkillRead, id=3)

        response = await client.put("/skills/3", json={"description": "new", "content": "body"})

        assert response.status_code == 200
        service.update_global_skill.assert_awaited_once_with(
            as_admin, 3, description="new", content="body"
        )

    async def test_partial_update_passes_none(self, client, service, as_admin, fake):
        service.update_global_skill.return_value = fake(SkillRead, id=3)

        await client.put("/skills/3", json={"description": "new"})

        service.update_global_skill.assert_awaited_once_with(
            as_admin, 3, description="new", content=None
        )

    @pytest.mark.parametrize("payload", [{"content": ""}, {"description": "x" * 256}])
    async def test_rejects_invalid_payload(self, client, service, as_admin, payload):
        response = await client.put("/skills/3", json=payload)

        assert response.status_code == 422
        service.update_global_skill.assert_not_awaited()

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.put("/skills/3", json={"description": "x"})

        assert response.status_code == 403
        service.update_global_skill.assert_not_awaited()

    async def test_not_found_returns_404(self, client, service, as_admin):
        service.update_global_skill.side_effect = NotFoundError("Skill not found")

        response = await client.put("/skills/3", json={"description": "x"})

        assert response.status_code == 404


@pytest.mark.parametrize("action,method", [("archive", "archive_skill"), ("restore", "restore_skill")])
class TestArchiveRestore:
    async def test_admin_can_call(self, client, service, as_admin, fake, action, method):
        getattr(service, method).return_value = fake(SkillRead, id=3)

        response = await client.post(f"/skills/3/{action}")

        assert response.status_code == 200
        getattr(service, method).assert_awaited_once_with(as_admin, 3)

    async def test_regular_user_is_forbidden(self, client, service, action, method):
        response = await client.post(f"/skills/3/{action}")

        assert response.status_code == 403
        getattr(service, method).assert_not_awaited()

    async def test_not_found_returns_404(self, client, service, as_admin, action, method):
        getattr(service, method).side_effect = NotFoundError("Skill not found")

        response = await client.post(f"/skills/3/{action}")

        assert response.status_code == 404