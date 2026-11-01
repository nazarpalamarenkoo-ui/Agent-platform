import pytest

from src.api.auth import auth as main_auth
from src.api.auth.admin import auth as admin_auth
from src.api.routers import my_tools
from src.db.db_connection import get_db
from src.db.enums.tool_auth_type import ToolAuthType

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    application = build_app(my_tools.router)
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


def tool_payload(**overrides):
    payload = {
        "tool_name": "my-search",
        "description": "Search my notes",
        "url": "https://example.com/search",
        "auth_type": ToolAuthType.NONE.value,
        "auth_description": None,
        "domain_ids": [],
    }
    payload.update(overrides)
    return payload


async def ids_of(client, **params):
    response = await client.get("/my/tools", params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


# --- authentication ---


@pytest.mark.parametrize(
    "method, url",
    [
        ("GET", "/my/tools"),
        ("POST", "/my/tools"),
        ("GET", "/my/tools/1"),
        ("PUT", "/my/tools/1"),
        ("POST", "/my/tools/1/archive"),
        ("POST", "/my/tools/1/restore"),
    ],
)
async def test_endpoints_require_authentication(client, method, url):
    response = await client.request(method, url)

    assert response.status_code == 401, response.text


# --- list ---


async def test_list_returns_only_own_tools(client, me, another_user, make_tool):
    mine = await make_tool(owner=me)
    foreign = await make_tool(owner=another_user)

    ids = await ids_of(client)

    assert mine.id in ids
    assert foreign.id not in ids


async def test_list_respects_limit(client, me, make_tool):
    await make_tool(owner=me)
    await make_tool(owner=me)

    response = await client.get("/my/tools", params={"limit": 1})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


async def test_list_offset_beyond_total_returns_empty_list(client, me, make_tool):
    await make_tool(owner=me)

    response = await client.get("/my/tools", params={"offset": 1000})

    assert response.status_code == 200, response.text
    assert response.json() == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
async def test_list_invalid_pagination_returns_422(client, me, params):
    response = await client.get("/my/tools", params=params)

    assert response.status_code == 422, response.text


# --- create ---


async def test_create_tool_returns_201_with_tool_and_warnings(client, me):
    response = await client.post("/my/tools", json=tool_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["tool"]["id"]
    assert body["tool"]["tool_name"] == "my-search"
    assert body["tool"]["url"] == "https://example.com/search"
    assert body["tool"]["archived_at"] is None
    assert isinstance(body["warnings"], list)


async def test_created_tool_is_listed_and_fetchable(client, me):
    created = await client.post("/my/tools", json=tool_payload())
    assert created.status_code == 201, created.text
    tool_id = created.json()["tool"]["id"]

    fetched = await client.get(f"/my/tools/{tool_id}")

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == tool_id
    assert tool_id in await ids_of(client)


@pytest.mark.parametrize("auth_type", list(ToolAuthType))
async def test_create_tool_keeps_auth_type(client, me, auth_type):
    payload = tool_payload(auth_type=auth_type.value, auth_description="how to authenticate")

    response = await client.post("/my/tools", json=payload)

    assert response.status_code == 201, response.text
    assert response.json()["tool"]["auth_type"] == auth_type.value


async def test_create_tool_with_domain_returns_201(client, me, sample_knowledge_domain):
    response = await client.post("/my/tools", json=tool_payload(domain_ids=[sample_knowledge_domain.id]))

    assert response.status_code == 201, response.text


async def test_create_tool_with_unknown_domain_is_rejected(client, me):
    response = await client.post("/my/tools", json=tool_payload(domain_ids=[999999]))

    assert response.status_code in (400, 404), response.text
    assert "999999" in response.json()["detail"]


async def test_create_tool_duplicate_name_is_rejected(client, me, make_tool):
    existing = await make_tool(owner=me)

    response = await client.post("/my/tools", json=tool_payload(tool_name=existing.tool_name))

    assert response.status_code in (400, 409), response.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"tool_name": ""},
        {"tool_name": "x" * 101},
        {"description": ""},
        {"description": "x" * 256},
        {"url": ""},
        {"url": "x" * 2049},
        {"auth_type": "not-a-real-auth-type"},
        {"auth_description": "x" * 256},
    ],
)
async def test_create_tool_invalid_payload_returns_422(client, me, overrides):
    response = await client.post("/my/tools", json=tool_payload(**overrides))

    assert response.status_code == 422, response.text


async def test_create_tool_missing_required_fields_returns_422(client, me):
    response = await client.post("/my/tools", json={"tool_name": "only-name"})

    assert response.status_code == 422, response.text


# --- read ---


async def test_get_own_tool_returns_tool(client, me, make_tool):
    tool = await make_tool(owner=me)

    response = await client.get(f"/my/tools/{tool.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == tool.id
    assert body["tool_name"] == tool.tool_name
    assert body["url"] == tool.url


async def test_get_foreign_tool_is_not_exposed(client, me, another_user, make_tool):
    foreign = await make_tool(owner=another_user)

    response = await client.get(f"/my/tools/{foreign.id}")

    assert response.status_code in (403, 404), response.text


async def test_get_unknown_tool_returns_404(client, me):
    response = await client.get("/my/tools/999999")

    assert response.status_code == 404, response.text


# --- update ---


async def test_update_tool_changes_description_and_url(client, me, make_tool):
    tool = await make_tool(owner=me)

    response = await client.put(
        f"/my/tools/{tool.id}",
        json={"description": "Changed", "url": "https://example.com/v2"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool"]["description"] == "Changed"
    assert body["tool"]["url"] == "https://example.com/v2"
    assert isinstance(body["warnings"], list)
    fetched = await client.get(f"/my/tools/{tool.id}")
    assert fetched.json()["description"] == "Changed"


async def test_update_tool_is_partial(client, me, make_tool):
    tool = await make_tool(owner=me)

    response = await client.put(f"/my/tools/{tool.id}", json={"description": "Changed"})

    assert response.status_code == 200, response.text
    assert response.json()["tool"]["url"] == tool.url
    assert response.json()["tool"]["tool_name"] == tool.tool_name


@pytest.mark.parametrize(
    "body", [{"description": ""}, {"url": ""}, {"auth_type": "nope"}, {"description": "x" * 256}]
)
async def test_update_tool_invalid_payload_returns_422(client, me, make_tool, body):
    tool = await make_tool(owner=me)

    response = await client.put(f"/my/tools/{tool.id}", json=body)

    assert response.status_code == 422, response.text


async def test_update_foreign_tool_is_rejected_and_unchanged(client, me, another_user, make_tool):
    foreign = await make_tool(owner=another_user)

    response = await client.put(f"/my/tools/{foreign.id}", json={"description": "Hacked"})

    assert response.status_code in (403, 404), response.text
    assert foreign.description != "Hacked"


async def test_update_unknown_tool_returns_404(client, me):
    response = await client.put("/my/tools/999999", json={"description": "Changed"})

    assert response.status_code == 404, response.text


# --- archive / restore ---


async def test_archived_tool_is_hidden_unless_include_archived(client, me, make_tool):
    tool = await make_tool(owner=me)

    response = await client.post(f"/my/tools/{tool.id}/archive")

    assert response.status_code == 200, response.text
    assert response.json()["archived_at"] is not None
    assert tool.id not in await ids_of(client)
    assert tool.id in await ids_of(client, include_archived=True)


async def test_restore_tool_makes_it_visible_again(client, me, make_tool):
    tool = await make_tool(owner=me)
    await client.post(f"/my/tools/{tool.id}/archive")

    response = await client.post(f"/my/tools/{tool.id}/restore")

    assert response.status_code == 200, response.text
    assert response.json()["archived_at"] is None
    assert tool.id in await ids_of(client)


async def test_archive_foreign_tool_is_rejected(client, me, another_user, make_tool, db_session):
    foreign = await make_tool(owner=another_user)

    response = await client.post(f"/my/tools/{foreign.id}/archive")

    assert response.status_code in (403, 404), response.text
    await db_session.refresh(foreign)
    assert foreign.archived_at is None


@pytest.mark.parametrize("action", ["archive", "restore"])
async def test_archive_and_restore_unknown_tool_return_404(client, me, action):
    response = await client.post(f"/my/tools/999999/{action}")

    assert response.status_code == 404, response.text