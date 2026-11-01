from unittest.mock import AsyncMock

import pytest

from src.api.auth import auth as main_auth
from src.api.auth.admin import auth as admin_auth
from src.api.routers import user_skills
from src.api.routers.errors import too_many_requests
from src.api.routers.rate_limit import enforce_draft_rate_limit
from src.db.db_connection import get_db
from src.db.enums.skill_visibility import SkillVisibility
from src.dependencies import get_skill_draft_service
from src.schemas.skill_drafts import SkillDraftResult, SkillDraftStatus
from src.services.errors import ConflictError, NotFoundError
from src.services.skill_draft_service import DraftQueueError, SkillDraftService

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def draft_service():
    return AsyncMock(spec=SkillDraftService)


@pytest.fixture
def app(db_session, build_app, draft_service):
    application = build_app(user_skills.router)
    application.dependency_overrides[get_db] = lambda: db_session
    application.dependency_overrides[get_skill_draft_service] = lambda: draft_service
    application.dependency_overrides[enforce_draft_rate_limit] = lambda: None
    return application


@pytest.fixture
def login(app):
    def _login(user):
        for dependency in (main_auth.get_current_user, admin_auth.get_current_user):
            app.dependency_overrides[dependency] = lambda: user
        return user

    return _login


@pytest.fixture
def me(sample_user, login):
    return login(sample_user)


def skill_payload(**overrides):
    payload = {
        "skill_name": "my-review",
        "description": "Review my code",
        "content": "Check naming and tests.",
        "domain_ids": [],
    }
    payload.update(overrides)
    return payload


async def ids_of(client, **params):
    response = await client.get("/my/skills", params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


# --- authentication ---


@pytest.mark.parametrize(
    "method, url",
    [
        ("GET", "/my/skills"),
        ("POST", "/my/skills"),
        ("POST", "/my/skills/import"),
        ("POST", "/my/skills/drafts"),
        ("GET", "/my/skills/drafts/1"),
        ("POST", "/my/skills/drafts/1/confirm"),
        ("GET", "/my/skills/1"),
        ("PUT", "/my/skills/1"),
        ("POST", "/my/skills/1/archive"),
        ("POST", "/my/skills/1/restore"),
        ("GET", "/my/skills/1/download"),
    ],
)
async def test_endpoints_require_authentication(client, method, url):
    response = await client.request(method, url)

    assert response.status_code == 401, response.text


# --- list ---


async def test_list_returns_only_own_skills(client, me, another_user, make_skill):
    mine = await make_skill(owner=me)
    foreign = await make_skill(owner=another_user)

    ids = await ids_of(client)

    assert mine.id in ids
    assert foreign.id not in ids


async def test_list_returns_summaries_without_content(client, me, make_skill):
    await make_skill(owner=me)

    item = (await client.get("/my/skills")).json()[0]

    assert {"id", "skill_name", "description", "content_hash", "visibility", "archived_at"} <= item.keys()
    assert "content" not in item


async def test_list_respects_limit_and_offset(client, me, make_skill):
    await make_skill(owner=me)
    await make_skill(owner=me)

    limited = await client.get("/my/skills", params={"limit": 1})
    beyond = await client.get("/my/skills", params={"offset": 1000})

    assert len(limited.json()) == 1
    assert beyond.json() == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
async def test_list_invalid_pagination_returns_422(client, me, params):
    response = await client.get("/my/skills", params=params)

    assert response.status_code == 422, response.text


# --- create ---


async def test_create_skill_returns_private_skill(client, me):
    response = await client.post("/my/skills", json=skill_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"]
    assert body["skill_name"] == "my-review"
    assert body["content"] == "Check naming and tests."
    assert body["content_hash"]
    assert body["visibility"] == SkillVisibility.PRIVATE.value
    assert body["archived_at"] is None


async def test_created_skill_is_listed_and_fetchable(client, me):
    created = await client.post("/my/skills", json=skill_payload())
    skill_id = created.json()["id"]

    fetched = await client.get(f"/my/skills/{skill_id}")

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == skill_id
    assert skill_id in await ids_of(client)


async def test_create_skill_with_domain_returns_201(client, me, sample_knowledge_domain):
    response = await client.post("/my/skills", json=skill_payload(domain_ids=[sample_knowledge_domain.id]))

    assert response.status_code == 201, response.text


async def test_create_skill_with_unknown_domain_is_rejected(client, me):
    response = await client.post("/my/skills", json=skill_payload(domain_ids=[999999]))

    assert response.status_code in (400, 404), response.text
    assert "999999" in response.json()["detail"]


async def test_create_skill_duplicate_name_is_rejected(client, me, make_skill):
    existing = await make_skill(owner=me)

    response = await client.post("/my/skills", json=skill_payload(skill_name=existing.skill_name))

    assert response.status_code in (400, 409), response.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"skill_name": ""},
        {"skill_name": "x" * 101},
        {"description": ""},
        {"description": "x" * 256},
        {"content": ""},
        {"content": "x" * 50_001},
    ],
)
async def test_create_skill_invalid_payload_returns_422(client, me, overrides):
    response = await client.post("/my/skills", json=skill_payload(**overrides))

    assert response.status_code == 422, response.text


# --- import ---


async def test_import_markdown_creates_skill(client, me):
    payload = {
        "markdown": "# Steps\nDo the thing carefully.",
        "skill_name": "imported-skill",
        "description": "Imported from markdown",
    }

    response = await client.post("/my/skills/import", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["skill_name"] == "imported-skill"
    assert body["description"] == "Imported from markdown"
    assert "Do the thing carefully." in body["content"]


async def test_import_duplicate_name_is_rejected(client, me, make_skill):
    existing = await make_skill(owner=me)
    payload = {"markdown": "# Steps", "skill_name": existing.skill_name, "description": "dup"}

    response = await client.post("/my/skills/import", json=payload)

    assert response.status_code in (400, 409), response.text


@pytest.mark.parametrize(
    "markdown",
    [pytest.param("", id="empty"), pytest.param("x" * 60_001, id="too-long")],
)
async def test_import_invalid_markdown_length_returns_422(client, me, markdown):
    response = await client.post("/my/skills/import", json={"markdown": markdown})

    assert response.status_code == 422, response.text


# --- read ---


async def test_get_own_skill_returns_full_skill(client, me, make_skill):
    skill = await make_skill(owner=me)

    response = await client.get(f"/my/skills/{skill.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == skill.id
    assert body["content"] == skill.content
    assert body["created_at"] and body["updated_at"]


async def test_get_foreign_skill_is_not_exposed(client, me, another_user, make_skill):
    foreign = await make_skill(owner=another_user)

    response = await client.get(f"/my/skills/{foreign.id}")

    assert response.status_code in (403, 404), response.text
    assert foreign.content not in response.text


async def test_get_unknown_skill_returns_404(client, me):
    response = await client.get("/my/skills/999999")

    assert response.status_code == 404, response.text


# --- update ---


async def test_update_skill_changes_fields_and_content_hash(client, me, make_skill):
    skill = await make_skill(owner=me)
    old_hash = skill.content_hash

    response = await client.put(
        f"/my/skills/{skill.id}",
        json={"skill_name": "renamed", "description": "Changed", "content": "New content"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skill_name"] == "renamed"
    assert body["description"] == "Changed"
    assert body["content"] == "New content"
    assert body["content_hash"] != old_hash


async def test_update_skill_is_partial(client, me, make_skill):
    skill = await make_skill(owner=me)

    response = await client.put(f"/my/skills/{skill.id}", json={"description": "Changed"})

    assert response.status_code == 200, response.text
    assert response.json()["content"] == skill.content
    assert response.json()["skill_name"] == skill.skill_name


async def test_update_skill_to_existing_name_is_rejected(client, me, make_skill):
    first = await make_skill(owner=me)
    second = await make_skill(owner=me)

    response = await client.put(f"/my/skills/{second.id}", json={"skill_name": first.skill_name})

    assert response.status_code in (400, 409), response.text


@pytest.mark.parametrize(
    "body",
    [{"skill_name": ""}, {"description": ""}, {"content": ""}, {"content": "x" * 50_001}],
)
async def test_update_skill_invalid_payload_returns_422(client, me, make_skill, body):
    skill = await make_skill(owner=me)

    response = await client.put(f"/my/skills/{skill.id}", json=body)

    assert response.status_code == 422, response.text


async def test_update_foreign_skill_is_rejected_and_unchanged(client, me, another_user, make_skill):
    foreign = await make_skill(owner=another_user)

    response = await client.put(f"/my/skills/{foreign.id}", json={"content": "Hacked"})

    assert response.status_code in (403, 404), response.text
    assert foreign.content != "Hacked"


async def test_update_unknown_skill_returns_404(client, me):
    response = await client.put("/my/skills/999999", json={"description": "Changed"})

    assert response.status_code == 404, response.text


# --- archive / restore ---


async def test_archived_skill_is_hidden_unless_include_archived(client, me, make_skill):
    skill = await make_skill(owner=me)

    response = await client.post(f"/my/skills/{skill.id}/archive")

    assert response.status_code == 200, response.text
    assert response.json()["archived_at"] is not None
    assert skill.id not in await ids_of(client)
    assert skill.id in await ids_of(client, include_archived=True)


async def test_restore_skill_makes_it_visible_again(client, me, make_skill):
    skill = await make_skill(owner=me)
    await client.post(f"/my/skills/{skill.id}/archive")

    response = await client.post(f"/my/skills/{skill.id}/restore")

    assert response.status_code == 200, response.text
    assert response.json()["archived_at"] is None
    assert skill.id in await ids_of(client)


async def test_archive_foreign_skill_is_rejected(client, me, another_user, make_skill, db_session):
    foreign = await make_skill(owner=another_user)

    response = await client.post(f"/my/skills/{foreign.id}/archive")

    assert response.status_code in (403, 404), response.text
    await db_session.refresh(foreign)
    assert foreign.archived_at is None


@pytest.mark.parametrize("action", ["archive", "restore"])
async def test_archive_and_restore_unknown_skill_return_404(client, me, action):
    response = await client.post(f"/my/skills/999999/{action}")

    assert response.status_code == 404, response.text


# --- download ---


async def test_download_skill_returns_markdown_attachment(client, me, make_skill):
    skill = await make_skill(owner=me)

    response = await client.get(f"/my/skills/{skill.id}/download")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="SKILL.md"'
    assert skill.content in response.text


async def test_download_foreign_skill_is_rejected(client, me, another_user, make_skill):
    foreign = await make_skill(owner=another_user)

    response = await client.get(f"/my/skills/{foreign.id}/download")

    assert response.status_code in (403, 404), response.text
    assert foreign.content not in response.text


async def test_download_unknown_skill_returns_404(client, me):
    response = await client.get("/my/skills/999999/download")

    assert response.status_code == 404, response.text


# --- drafts (SkillDraftService is mocked: it needs the queue and an LLM) ---


async def test_request_draft_returns_202_with_job(client, me, draft_service):
    draft_service.request_draft.return_value = (7, "pending")

    response = await client.post("/my/skills/drafts", json={"intent": "Summarize pull requests"})

    assert response.status_code == 202, response.text
    assert response.json() == {"job_id": 7, "status": "pending"}
    actor_arg, request_arg = draft_service.request_draft.await_args.args
    assert actor_arg.id == me.id
    assert request_arg.intent == "Summarize pull requests"
    assert request_arg.auto_packs is False


async def test_request_draft_queue_failure_returns_503(client, me, draft_service):
    draft_service.request_draft.side_effect = DraftQueueError("redis down")

    response = await client.post("/my/skills/drafts", json={"intent": "Summarize"})

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "Queue unavailable"
    assert "redis down" not in response.text


@pytest.mark.parametrize(
    "error, expected",
    [(NotFoundError("Config bundle 5 not found"), 404), (ValueError("bad intent"), 400)],
)
async def test_request_draft_service_errors_are_mapped(client, me, draft_service, error, expected):
    draft_service.request_draft.side_effect = error

    response = await client.post("/my/skills/drafts", json={"intent": "Summarize"})

    assert response.status_code == expected, response.text
    assert response.json()["detail"] == str(error)


@pytest.mark.parametrize(
    "overrides",
    [
        {"intent": ""},
        {"intent": "x" * 2001},
        {"skill_name": "x" * 101},
        {"description": "x" * 256},
        {"source_text": "x" * 20_001},
        {"knowledge_pack_ids": list(range(1, 12))},
        {"search_queries": ["a", "b", "c", "d"]},
    ],
)
async def test_request_draft_invalid_payload_returns_422(client, me, draft_service, overrides):
    response = await client.post("/my/skills/drafts", json={"intent": "Summarize", **overrides})

    assert response.status_code == 422, response.text
    draft_service.request_draft.assert_not_awaited()


async def test_request_draft_is_blocked_by_rate_limit(app, client, me, draft_service):
    def deny():
        raise too_many_requests(retry_after=42)

    app.dependency_overrides[enforce_draft_rate_limit] = deny

    response = await client.post("/my/skills/drafts", json={"intent": "Summarize"})

    assert response.status_code == 429, response.text
    assert response.headers["retry-after"] == "42"
    draft_service.request_draft.assert_not_awaited()


async def test_get_draft_returns_status_and_result(client, me, draft_service):
    draft_service.get_status.return_value = SkillDraftStatus(
        job_id=7,
        status="done",
        draft=SkillDraftResult(
            skill_name="drafted", description="Drafted skill", content="# body", grounded=True
        ),
    )

    response = await client.get("/my/skills/drafts/7")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == 7
    assert body["status"] == "done"
    assert body["draft"]["skill_name"] == "drafted"
    assert body["draft"]["grounded"] is True
    assert draft_service.get_status.await_args.args[1] == 7


async def test_get_unknown_draft_returns_404(client, me, draft_service):
    draft_service.get_status.side_effect = NotFoundError("Draft job 9 not found")

    response = await client.get("/my/skills/drafts/9")

    assert response.status_code == 404, response.text


async def test_confirm_draft_returns_created_skill(client, me, draft_service, make_skill):
    skill = await make_skill(owner=me)
    draft_service.confirm.return_value = skill

    response = await client.post("/my/skills/drafts/7/confirm", json={"skill_name": "final-name"})

    assert response.status_code == 201, response.text
    assert response.json()["id"] == skill.id
    actor_arg, job_id_arg, body_arg = draft_service.confirm.await_args.args
    assert (actor_arg.id, job_id_arg, body_arg.skill_name) == (me.id, 7, "final-name")


@pytest.mark.parametrize(
    "error, expected",
    [
        (NotFoundError("Draft job 7 not found"), 404),
        (ConflictError("Draft already confirmed"), 409),
        (ValueError("Draft is not ready"), 400),
    ],
)
async def test_confirm_draft_errors_are_mapped(client, me, draft_service, error, expected):
    draft_service.confirm.side_effect = error

    response = await client.post("/my/skills/drafts/7/confirm", json={})

    assert response.status_code == expected, response.text


@pytest.mark.parametrize(
    "body",
    [{"skill_name": ""}, {"description": ""}, {"content": ""}, {"content": "x" * 50_001}],
)
async def test_confirm_draft_invalid_payload_returns_422(client, me, draft_service, body):
    response = await client.post("/my/skills/drafts/7/confirm", json=body)

    assert response.status_code == 422, response.text
    draft_service.confirm.assert_not_awaited()