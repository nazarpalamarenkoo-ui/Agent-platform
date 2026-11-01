from datetime import datetime, timezone

import pytest
import pytest_asyncio

from src.api.auth import auth as main_auth
from src.api.auth.admin import auth as admin_auth
from src.api.routers import user_content
from src.db.db_connection import get_db
from src.db.enums.user_role import UserRole

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    application = build_app(user_content.router)
    application.dependency_overrides[get_db] = lambda: db_session
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


@pytest_asyncio.fixture
async def admin_user(make_user, login):
    return login(await make_user(role=UserRole.ADMIN))


async def skill_ids(client, user_id, **params):
    response = await client.get(f"/admin/users/{user_id}/skills", params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


async def tool_ids(client, user_id, **params):
    response = await client.get(f"/admin/users/{user_id}/tools", params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


ADMIN_ENDPOINTS = [
    ("GET", "/admin/users/1/overview", None),
    ("GET", "/admin/users/1/skills", None),
    ("GET", "/admin/users/1/skills/1", None),
    ("POST", "/admin/users/1/skills/1/archive", {"reason": "spam"}),
    ("GET", "/admin/users/1/tools", None),
]




@pytest.mark.parametrize("method, url, body", ADMIN_ENDPOINTS)
async def test_endpoints_require_authentication(client, method, url, body):
    response = await client.request(method, url, json=body)

    assert response.status_code == 401, response.text


@pytest.mark.parametrize("method, url, body", ADMIN_ENDPOINTS)
async def test_endpoints_reject_regular_user(client, me, method, url, body):
    response = await client.request(method, url, json=body)

    assert response.status_code == 403, response.text




async def test_overview_counts_private_content_of_user(
    client, admin_user, sample_user, another_user, make_skill, make_tool
):
    await make_skill(owner=sample_user)
    await make_skill(owner=sample_user)
    await make_tool(owner=sample_user)
    await make_skill(owner=another_user)

    response = await client.get(f"/admin/users/{sample_user.id}/overview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == sample_user.id
    assert body["private_skills"] == 2
    assert body["private_tools"] == 1
    assert {"bundles", "token_events", "tokens_used", "token_limit"} <= body.keys()


async def test_overview_unknown_user_returns_404(client, admin_user):
    response = await client.get("/admin/users/999999/overview")

    assert response.status_code == 404, response.text




async def test_list_skills_returns_only_skills_of_requested_user(
    client, admin_user, sample_user, another_user, make_skill
):
    mine = await make_skill(owner=sample_user)
    foreign = await make_skill(owner=another_user)

    ids = await skill_ids(client, sample_user.id)

    assert mine.id in ids
    assert foreign.id not in ids


async def test_list_skills_respects_limit_and_offset(client, admin_user, sample_user, make_skill):
    await make_skill(owner=sample_user)
    await make_skill(owner=sample_user)

    limited = await client.get(f"/admin/users/{sample_user.id}/skills", params={"limit": 1})
    beyond = await client.get(f"/admin/users/{sample_user.id}/skills", params={"offset": 1000})

    assert len(limited.json()) == 1
    assert beyond.json() == []


async def test_list_skills_unknown_user_returns_404(client, admin_user):
    response = await client.get("/admin/users/999999/skills")

    assert response.status_code == 404, response.text


async def test_get_skill_returns_content_and_owner(client, admin_user, sample_user, make_skill):
    skill = await make_skill(owner=sample_user)

    response = await client.get(f"/admin/users/{sample_user.id}/skills/{skill.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == skill.id
    assert body["content"] == skill.content
    assert body["owner_id"] == sample_user.id


async def test_get_skill_of_another_user_returns_404(
    client, admin_user, sample_user, another_user, make_skill
):
    foreign = await make_skill(owner=another_user)

    response = await client.get(f"/admin/users/{sample_user.id}/skills/{foreign.id}")

    assert response.status_code in (403, 404), response.text
    assert foreign.content not in response.text


async def test_get_unknown_skill_returns_404(client, admin_user, sample_user):
    response = await client.get(f"/admin/users/{sample_user.id}/skills/999999")

    assert response.status_code == 404, response.text




@pytest.mark.xfail(strict=True, reason="archive endpoint returns 500 (service bug)")
async def test_archive_for_violation_archives_skill(client, admin_user, sample_user, make_skill):
    skill = await make_skill(owner=sample_user)

    response = await client.post(
        f"/admin/users/{sample_user.id}/skills/{skill.id}/archive", json={"reason": "spam"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == skill.id
    assert response.json()["archived_at"] is not None


async def test_archived_skill_is_hidden_unless_include_archived(
    client, admin_user, sample_user, make_skill
):
    skill = await make_skill(owner=sample_user)
    await client.post(f"/admin/users/{sample_user.id}/skills/{skill.id}/archive", json={"reason": "spam"})

    assert skill.id not in await skill_ids(client, sample_user.id)
    assert skill.id in await skill_ids(client, sample_user.id, include_archived=True)


@pytest.mark.parametrize("reason", ["", "x" * 256])
async def test_archive_with_invalid_reason_returns_422(
    client, admin_user, sample_user, make_skill, reason
):
    skill = await make_skill(owner=sample_user)

    response = await client.post(
        f"/admin/users/{sample_user.id}/skills/{skill.id}/archive", json={"reason": reason}
    )

    assert response.status_code == 422, response.text


async def test_archive_without_reason_returns_422(client, admin_user, sample_user, make_skill):
    skill = await make_skill(owner=sample_user)

    response = await client.post(f"/admin/users/{sample_user.id}/skills/{skill.id}/archive", json={})

    assert response.status_code == 422, response.text


async def test_archive_skill_of_another_user_is_rejected(
    client, admin_user, sample_user, another_user, make_skill, db_session
):
    foreign = await make_skill(owner=another_user)

    response = await client.post(
        f"/admin/users/{sample_user.id}/skills/{foreign.id}/archive", json={"reason": "spam"}
    )

    assert response.status_code in (403, 404), response.text
    await db_session.refresh(foreign)
    assert foreign.archived_at is None


async def test_global_skill_cannot_be_archived_through_user_content(
    client, admin_user, sample_user, make_skill, db_session
):
    global_skill = await make_skill()

    response = await client.post(
        f"/admin/users/{sample_user.id}/skills/{global_skill.id}/archive", json={"reason": "spam"}
    )

    assert response.status_code in (403, 404), response.text
    await db_session.refresh(global_skill)
    assert global_skill.archived_at is None


async def test_archive_unknown_skill_returns_404(client, admin_user, sample_user):
    response = await client.post(
        f"/admin/users/{sample_user.id}/skills/999999/archive", json={"reason": "spam"}
    )

    assert response.status_code == 404, response.text




async def test_list_tools_returns_only_tools_of_requested_user(
    client, admin_user, sample_user, another_user, make_tool
):
    mine = await make_tool(owner=sample_user)
    foreign = await make_tool(owner=another_user)

    ids = await tool_ids(client, sample_user.id)

    assert mine.id in ids
    assert foreign.id not in ids


@pytest.mark.xfail(strict=True, reason="url_masked leaks user:password (service bug)")
async def test_list_tools_does_not_expose_raw_url(client, admin_user, sample_user, make_tool):
    await make_tool(owner=sample_user, url="https://user:secret@example.com/tool?token=abc")

    response = await client.get(f"/admin/users/{sample_user.id}/tools")

    item = response.json()[0]
    assert "url" not in item
    assert item["url_masked"]
    assert "secret" not in response.text


async def test_archived_tool_is_hidden_unless_include_archived(
    client, admin_user, sample_user, make_tool, db_session
):
    tool = await make_tool(owner=sample_user)
    tool.archived_at = datetime.now(timezone.utc)
    await db_session.commit()

    assert tool.id not in await tool_ids(client, sample_user.id)
    assert tool.id in await tool_ids(client, sample_user.id, include_archived=True)


async def test_list_tools_unknown_user_returns_404(client, admin_user):
    response = await client.get("/admin/users/999999/tools")

    assert response.status_code == 404, response.text