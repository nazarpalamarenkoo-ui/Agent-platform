import pytest

from src.api.routers import user_content
from src.dependencies import get_admin_user_content_service
from src.schemas.admin_skills import (
    AdminSkillListItem,
    AdminSkillRead,
    AdminToolItem,
    UserOverview,
)
from src.services.admin_user_content_service import AdminUserContentService
from src.services.errors import ForbiddenError, NotFoundError

pytestmark = pytest.mark.unit

ROUTER = user_content.router
SERVICE_DEPENDENCY = get_admin_user_content_service
SERVICE_SPEC = AdminUserContentService

ENDPOINTS = [
    ("get", "/admin/users/5/overview", "overview", None),
    ("get", "/admin/users/5/skills", "list_skills", None),
    ("get", "/admin/users/5/skills/9", "get_skill", None),
    ("post", "/admin/users/5/skills/9/archive", "archive_for_violation", {"reason": "spam"}),
    ("get", "/admin/users/5/tools", "list_tools", None),
]
ENDPOINT_IDS = [e[2] for e in ENDPOINTS]


@pytest.mark.parametrize("verb,url,method,body", ENDPOINTS, ids=ENDPOINT_IDS)
class TestAccessAndErrors:
    async def test_regular_user_is_forbidden(self, client, service, verb, url, method, body):
        response = await getattr(client, verb)(url, **({"json": body} if body else {}))

        assert response.status_code == 403
        getattr(service, method).assert_not_awaited()

    @pytest.mark.parametrize("error,code", [(NotFoundError("nf"), 404), (ForbiddenError("fb"), 403)])
    async def test_maps_service_errors(
        self, client, service, as_admin, verb, url, method, body, error, code
    ):
        getattr(service, method).side_effect = error

        response = await getattr(client, verb)(url, **({"json": body} if body else {}))

        assert response.status_code == code
        assert response.json()["detail"] == str(error)


async def test_overview(client, service, as_admin, fake):
    service.overview.return_value = fake(UserOverview, user_id=5, private_skills=2)

    response = await client.get("/admin/users/5/overview")

    assert response.status_code == 200
    assert response.json()["private_skills"] == 2
    service.overview.assert_awaited_once_with(as_admin, 5)


async def test_list_skills_uses_defaults(client, service, as_admin, fake):
    service.list_skills.return_value = [fake(AdminSkillListItem, id=1)]

    response = await client.get("/admin/users/5/skills")

    assert response.status_code == 200
    assert [s["id"] for s in response.json()] == [1]
    service.list_skills.assert_awaited_once_with(as_admin, 5, False, 100, 0)


async def test_list_skills_passes_query_params(client, service, as_admin):
    service.list_skills.return_value = []

    await client.get(
        "/admin/users/5/skills", params={"include_archived": True, "limit": 10, "offset": 20}
    )

    service.list_skills.assert_awaited_once_with(as_admin, 5, True, 10, 20)


async def test_get_skill_returns_content(client, service, as_admin, fake):
    service.get_skill.return_value = fake(AdminSkillRead, id=9, content="full body")

    response = await client.get("/admin/users/5/skills/9")

    assert response.status_code == 200
    assert response.json()["content"] == "full body"
    service.get_skill.assert_awaited_once_with(as_admin, 5, 9)


class TestArchiveForViolation:
    async def test_archives_with_reason(self, client, service, as_admin, fake):
        service.archive_for_violation.return_value = fake(AdminSkillListItem, id=9)

        response = await client.post("/admin/users/5/skills/9/archive", json={"reason": "spam"})

        assert response.status_code == 200
        service.archive_for_violation.assert_awaited_once_with(as_admin, 5, 9, "spam")

    @pytest.mark.parametrize("payload", [{}, {"reason": ""}, {"reason": "r" * 256}])
    async def test_rejects_invalid_reason(self, client, service, as_admin, payload):
        response = await client.post("/admin/users/5/skills/9/archive", json=payload)

        assert response.status_code == 422
        service.archive_for_violation.assert_not_awaited()


async def test_list_tools_returns_masked_urls(client, service, as_admin, fake):
    service.list_tools.return_value = [
        fake(AdminToolItem, id=1, url_masked="https://example.com/p?***")
    ]

    response = await client.get("/admin/users/5/tools", params={"include_archived": True})

    assert response.status_code == 200
    assert response.json()[0]["url_masked"] == "https://example.com/p?***"
    service.list_tools.assert_awaited_once_with(as_admin, 5, True)