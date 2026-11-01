from unittest.mock import AsyncMock, create_autospec

import pytest

from src.api.routers import rate_limit, user_skills
from src.api.routers.errors import too_many_requests
from src.dependencies import get_arq_pool, get_skill_draft_service, get_user_skill_service
from src.schemas.skill_drafts import SkillDraftStatus
from src.schemas.user_skills import MySkillRead, MySkillSummary
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.skill_draft_service import DraftQueueError, SkillDraftService
from src.services.user_skill_service import UserSkillService

pytestmark = pytest.mark.unit

ROUTER = user_skills.router
SERVICE_DEPENDENCY = get_user_skill_service
SERVICE_SPEC = UserSkillService

CREATE = {
    "skill_name": "my-skill",
    "description": "desc",
    "content": "# Body",
    "domain_ids": [1, 2],
}
IMPORT = {
    "markdown": "---\nname: x\n---\nbody",
    "skill_name": "my-skill",
    "description": "desc",
    "domain_ids": [1],
}
DRAFT = {"intent": "skill for reviewing pull requests"}
CONFIRM = {"skill_name": "pr-review", "description": "d", "content": "# c", "domain_ids": [1]}

ERRORS = [
    (NotFoundError("nf"), 404),
    (ForbiddenError("fb"), 403),
    (ConflictError("cf"), 409),
    (ValueError("bad"), 400),
]


@pytest.fixture
def draft_service(override):
    return override(get_skill_draft_service, create_autospec(SkillDraftService, instance=True))


@pytest.fixture
def rate_limit_check(monkeypatch, override):
    override(get_arq_pool, object())
    mock = AsyncMock()
    monkeypatch.setattr(rate_limit, "check_rate_limit", mock)
    return mock


class TestList:
    async def test_uses_defaults(self, client, service, actor, fake):
        service.list_skills.return_value = [fake(MySkillSummary, id=1), fake(MySkillSummary, id=2)]

        response = await client.get("/my/skills")

        assert response.status_code == 200
        assert [s["id"] for s in response.json()] == [1, 2]
        service.list_skills.assert_awaited_once_with(
            actor, limit=100, offset=0, include_archived=False
        )

    async def test_passes_query_params(self, client, service, actor):
        service.list_skills.return_value = []

        await client.get("/my/skills", params={"limit": 5, "offset": 2, "include_archived": True})

        service.list_skills.assert_awaited_once_with(actor, limit=5, offset=2, include_archived=True)

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
    async def test_rejects_invalid_pagination(self, client, service, params):
        response = await client.get("/my/skills", params=params)

        assert response.status_code == 422
        service.list_skills.assert_not_awaited()


class TestCreate:
    async def test_returns_201(self, client, service, actor, fake):
        service.create_skill.return_value = fake(MySkillRead, id=5)

        response = await client.post("/my/skills", json=CREATE)

        assert response.status_code == 201
        assert response.json()["id"] == 5
        service.create_skill.assert_awaited_once_with(actor, "my-skill", "desc", "# Body", [1, 2])

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, error, code):
        service.create_skill.side_effect = error

        response = await client.post("/my/skills", json=CREATE)

        assert response.status_code == code
        assert response.json()["detail"] == str(error)

    @pytest.mark.parametrize(
        "payload", [{}, {**CREATE, "skill_name": ["x"]}, {**CREATE, "domain_ids": ["x"]}]
    )
    async def test_rejects_invalid_payload(self, client, service, payload):
        response = await client.post("/my/skills", json=payload)

        assert response.status_code == 422
        service.create_skill.assert_not_awaited()


class TestImport:
    async def test_returns_201(self, client, service, actor, fake):
        service.import_markdown.return_value = fake(MySkillRead, id=6)

        response = await client.post("/my/skills/import", json=IMPORT)

        assert response.status_code == 201
        assert response.json()["id"] == 6
        service.import_markdown.assert_awaited_once_with(
            actor, IMPORT["markdown"], "my-skill", "desc", [1]
        )

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, error, code):
        service.import_markdown.side_effect = error

        response = await client.post("/my/skills/import", json=IMPORT)

        assert response.status_code == code

    @pytest.mark.parametrize("payload", [{}, {**IMPORT, "markdown": ["x"]}])
    async def test_rejects_invalid_payload(self, client, service, payload):
        response = await client.post("/my/skills/import", json=payload)

        assert response.status_code == 422
        service.import_markdown.assert_not_awaited()


class TestRequestDraft:
    async def test_returns_202_with_job(self, client, service, draft_service, rate_limit_check, actor):
        draft_service.request_draft.return_value = (7, "pending")

        response = await client.post("/my/skills/drafts", json=DRAFT)

        assert response.status_code == 202
        assert response.json() == {"job_id": 7, "status": "pending"}
        args = draft_service.request_draft.await_args.args
        assert args[0] is actor
        assert args[1].intent == DRAFT["intent"]
        assert args[1].knowledge_pack_ids == []
        assert args[1].auto_packs is False

    async def test_rate_limit_is_checked_per_user(
        self, client, service, draft_service, rate_limit_check, actor
    ):
        draft_service.request_draft.return_value = (7, "pending")

        await client.post("/my/skills/drafts", json=DRAFT)

        assert rate_limit_check.await_args.args[1] == f"ratelimit:draft:{actor.id}"

    async def test_rate_limit_exceeded_returns_429_and_skips_service(
        self, client, service, draft_service, rate_limit_check
    ):
        rate_limit_check.side_effect = too_many_requests(retry_after=42)

        response = await client.post("/my/skills/drafts", json=DRAFT)

        assert response.status_code == 429
        assert response.headers["retry-after"] == "42"
        draft_service.request_draft.assert_not_awaited()

    async def test_queue_error_returns_503(self, client, service, draft_service, rate_limit_check):
        draft_service.request_draft.side_effect = DraftQueueError()

        response = await client.post("/my/skills/drafts", json=DRAFT)

        assert response.status_code == 503
        assert response.json()["detail"] == "Queue unavailable"

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_value_errors(self, client, service, draft_service, rate_limit_check, error, code):
        draft_service.request_draft.side_effect = error

        response = await client.post("/my/skills/drafts", json=DRAFT)

        assert response.status_code == code

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"intent": ""},
            {"intent": "x" * 2001},
            {**DRAFT, "skill_name": "x" * 101},
            {**DRAFT, "description": "x" * 256},
            {**DRAFT, "source_text": "x" * 20_001},
            {**DRAFT, "knowledge_pack_ids": list(range(11))},
            {**DRAFT, "search_queries": ["a", "b", "c", "d"]},
            {**DRAFT, "config_bundle_id": "abc"},
        ],
    )
    async def test_rejects_invalid_payload(
        self, client, service, draft_service, rate_limit_check, payload
    ):
        response = await client.post("/my/skills/drafts", json=payload)

        assert response.status_code == 422
        draft_service.request_draft.assert_not_awaited()


class TestGetDraftStatus:
    async def test_returns_status(self, client, service, draft_service, actor, fake):
        draft_service.get_status.return_value = fake(SkillDraftStatus, job_id=5, status="running")

        response = await client.get("/my/skills/drafts/5")

        assert response.status_code == 200
        assert response.json()["job_id"] == 5
        assert response.json()["status"] == "running"
        assert response.json()["draft"] is None
        draft_service.get_status.assert_awaited_once_with(actor, 5)

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, draft_service, error, code):
        draft_service.get_status.side_effect = error

        response = await client.get("/my/skills/drafts/5")

        assert response.status_code == code

    async def test_invalid_job_id(self, client, service, draft_service):
        response = await client.get("/my/skills/drafts/abc")

        assert response.status_code == 422
        draft_service.get_status.assert_not_awaited()
        service.get_skill.assert_not_awaited()


class TestConfirmDraft:
    async def test_returns_201(self, client, service, draft_service, actor, fake):
        draft_service.confirm.return_value = fake(MySkillRead, id=9)

        response = await client.post("/my/skills/drafts/5/confirm", json=CONFIRM)

        assert response.status_code == 201
        assert response.json()["id"] == 9
        args = draft_service.confirm.await_args.args
        assert args[:2] == (actor, 5)
        assert args[2].skill_name == "pr-review"
        assert args[2].domain_ids == [1]

    async def test_empty_body_is_allowed(self, client, service, draft_service, fake):
        draft_service.confirm.return_value = fake(MySkillRead, id=9)

        response = await client.post("/my/skills/drafts/5/confirm", json={})

        assert response.status_code == 201
        assert draft_service.confirm.await_args.args[2].skill_name is None

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, draft_service, error, code):
        draft_service.confirm.side_effect = error

        response = await client.post("/my/skills/drafts/5/confirm", json={})

        assert response.status_code == code

    @pytest.mark.parametrize(
        "payload",
        [
            {"skill_name": ""},
            {"skill_name": "x" * 101},
            {"description": ""},
            {"content": ""},
            {"content": "x" * 50_001},
            {"domain_ids": ["x"]},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, draft_service, payload):
        response = await client.post("/my/skills/drafts/5/confirm", json=payload)

        assert response.status_code == 422
        draft_service.confirm.assert_not_awaited()


class TestGet:
    async def test_returns_skill(self, client, service, actor, fake):
        service.get_skill.return_value = fake(MySkillRead, id=9)

        response = await client.get("/my/skills/9")

        assert response.status_code == 200
        assert response.json()["id"] == 9
        service.get_skill.assert_awaited_once_with(actor, 9)

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, error, code):
        service.get_skill.side_effect = error

        response = await client.get("/my/skills/9")

        assert response.status_code == code

    async def test_invalid_id(self, client, service):
        response = await client.get("/my/skills/abc")

        assert response.status_code == 422
        service.get_skill.assert_not_awaited()


class TestUpdate:
    async def test_passes_all_fields(self, client, service, actor, fake):
        service.update_skill.return_value = fake(MySkillRead, id=3)

        response = await client.put(
            "/my/skills/3", json={"skill_name": "new", "description": "d", "content": "c"}
        )

        assert response.status_code == 200
        service.update_skill.assert_awaited_once_with(
            actor, 3, skill_name="new", description="d", content="c"
        )

    async def test_partial_update_passes_none(self, client, service, actor, fake):
        service.update_skill.return_value = fake(MySkillRead, id=3)

        await client.put("/my/skills/3", json={"description": "d"})

        service.update_skill.assert_awaited_once_with(
            actor, 3, skill_name=None, description="d", content=None
        )

    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, error, code):
        service.update_skill.side_effect = error

        response = await client.put("/my/skills/3", json={"description": "d"})

        assert response.status_code == code


class TestArchiveAndRestore:
    @pytest.mark.parametrize("action,method", [("archive", "archive_skill"), ("restore", "restore_skill")])
    async def test_calls_service(self, client, service, actor, fake, action, method):
        getattr(service, method).return_value = fake(MySkillRead, id=3)

        response = await client.post(f"/my/skills/3/{action}")

        assert response.status_code == 200
        getattr(service, method).assert_awaited_once_with(actor, 3)

    @pytest.mark.parametrize("action,method", [("archive", "archive_skill"), ("restore", "restore_skill")])
    @pytest.mark.parametrize("error,code", ERRORS)
    async def test_maps_errors(self, client, service, action, method, error, code):
        getattr(service, method).side_effect = error

        response = await client.post(f"/my/skills/3/{action}")

        assert response.status_code == code


class TestDownload:
    async def test_returns_markdown_attachment(self, client, service, actor):
        service.export_markdown.return_value = "---\nname: x\n---\nbody"

        response = await client.get("/my/skills/9/download")

        assert response.status_code == 200
        assert response.text == "---\nname: x\n---\nbody"
        assert response.headers["content-type"].startswith("text/markdown")
        assert response.headers["content-disposition"] == 'attachment; filename="SKILL.md"'
        service.export_markdown.assert_awaited_once_with(actor, 9)

    async def test_not_found(self, client, service):
        service.export_markdown.side_effect = NotFoundError("nf")

        response = await client.get("/my/skills/9/download")

        assert response.status_code == 404