from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.db.enums.notification_type import NotificationType
from src.db.enums.tool_auth_type import ToolAuthType
from src.db.enums.tool_visibility import ToolVisibility
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.tool_service import MAX_URL_LENGTH, ToolService

ADMIN = SimpleNamespace(id=1, is_admin=True)
USER = SimpleNamespace(id=2, is_admin=False)
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_tool(id=1, owner_id=None, archived=False):
    return SimpleNamespace(id=id, owner_id=owner_id, archived_at=NOW if archived else None)


@pytest.fixture
def tool_repo():
    repo = AsyncMock()
    repo.get_global_by_name.return_value = None
    return repo


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def bundle_repo():
    return AsyncMock()


@pytest.fixture
def notification_repo():
    return AsyncMock()


@pytest.fixture
def service(tool_repo, domain_repo, bundle_repo, notification_repo):
    return ToolService(tool_repo, domain_repo, bundle_repo, notification_repo)


class TestListTools:
    async def test_regular_listing(self, service, tool_repo):
        await service.list_tools(USER, limit=5, offset=1, domain_id=3)

        tool_repo.list_visible.assert_awaited_once_with(2, limit=5, offset=1, domain_id=3)

    async def test_include_archived_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.list_tools(USER, include_archived=True)

    async def test_admin_includes_archived(self, service, tool_repo):
        await service.list_tools(ADMIN, include_archived=True)

        tool_repo.admin_list_global.assert_awaited_once_with(limit=100, offset=0, include_archived=True)


class TestGetTool:
    async def test_returns_visible_tool(self, service, tool_repo):
        tool = make_tool()
        tool_repo.get_visible.return_value = tool

        assert await service.get_tool(USER, 1) is tool

    async def test_admin_can_see_archived_global_tool(self, service, tool_repo):
        tool = make_tool(archived=True)
        tool_repo.get_visible.return_value = None
        tool_repo.admin_get_by_id.return_value = tool

        assert await service.get_tool(ADMIN, 1) is tool

    async def test_admin_cannot_see_private_tool_of_other_user(self, service, tool_repo):
        tool_repo.get_visible.return_value = None
        tool_repo.admin_get_by_id.return_value = make_tool(owner_id=9)

        with pytest.raises(NotFoundError, match="Tool not found"):
            await service.get_tool(ADMIN, 1)

    async def test_regular_user_not_found(self, service, tool_repo):
        tool_repo.get_visible.return_value = None

        with pytest.raises(NotFoundError):
            await service.get_tool(USER, 1)

        tool_repo.admin_get_by_id.assert_not_awaited()


class TestCreateTool:
    async def test_requires_admin(self, service, tool_repo):
        with pytest.raises(ForbiddenError):
            await service.create_tool(USER, "n", "d", "https://x.io")

        tool_repo.create.assert_not_awaited()

    @pytest.mark.parametrize("name", ["", "  ", None])
    async def test_rejects_empty_name(self, service, name):
        with pytest.raises(ValueError, match="Tool name must not be empty"):
            await service.create_tool(ADMIN, name, "d", "https://x.io")

    async def test_rejects_invalid_url(self, service, tool_repo):
        with pytest.raises(ValueError, match="absolute http"):
            await service.create_tool(ADMIN, "n", "d", "ftp://x.io")

        tool_repo.create.assert_not_awaited()

    async def test_rejects_duplicate_name(self, service, tool_repo):
        tool_repo.get_global_by_name.return_value = make_tool()

        with pytest.raises(ConflictError, match="Tool 'n' already exists"):
            await service.create_tool(ADMIN, "n", "d", "https://x.io")

    async def test_creates_global_tool_with_domains(self, service, tool_repo, domain_repo):
        created = make_tool(id=9)
        tool_repo.create.return_value = created
        tool_repo.admin_get_by_id.return_value = created
        domain = SimpleNamespace(id=1)
        domain_repo.get_by_id.return_value = domain

        result = await service.create_tool(
            ADMIN, " n ", "desc", " https://x.io/api ",
            auth_type=ToolAuthType.NONE, auth_description="ad", domain_ids=[1, 1],
        )

        assert result is created
        tool_repo.create.assert_awaited_once_with(
            tool_name="n", description="desc", url="https://x.io/api",
            auth_type=ToolAuthType.NONE, auth_description="ad",
            visibility=ToolVisibility.GLOBAL, owner_id=None,
        )
        domain_repo.get_by_id.assert_awaited_once_with(1)
        tool_repo.add_domain.assert_awaited_once_with(created, domain)

    async def test_missing_domain_prevents_creation(self, service, tool_repo, domain_repo):
        domain_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Domain 3 not found"):
            await service.create_tool(ADMIN, "n", "d", "https://x.io", domain_ids=[3])

        tool_repo.create.assert_not_awaited()


class TestUpdateTool:
    async def test_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.update_tool(USER, 1, description="x")

    async def test_rejects_private_tool(self, service, tool_repo):
        tool_repo.admin_get_by_id.return_value = make_tool(owner_id=9)

        with pytest.raises(NotFoundError):
            await service.update_tool(ADMIN, 1, description="x")

    async def test_applies_only_given_fields(self, service, tool_repo):
        tool = make_tool()
        tool_repo.admin_get_by_id.return_value = tool

        await service.update_tool(
            ADMIN, 1, description="new", url=" https://y.io ",
            auth_type=ToolAuthType.NONE, auth_description="ad",
        )

        tool_repo.update.assert_awaited_once_with(
            tool, description="new", url="https://y.io",
            auth_type=ToolAuthType.NONE, auth_description="ad",
        )

    async def test_no_changes_no_update(self, service, tool_repo):
        tool_repo.admin_get_by_id.return_value = make_tool()

        await service.update_tool(ADMIN, 1)

        tool_repo.update.assert_not_awaited()

    async def test_invalid_url_is_rejected(self, service, tool_repo):
        tool_repo.admin_get_by_id.return_value = make_tool()

        with pytest.raises(ValueError, match="absolute http"):
            await service.update_tool(ADMIN, 1, url="not a url")

        tool_repo.update.assert_not_awaited()


class TestArchiveRestoreTool:
    async def test_archive_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.archive_tool(USER, 1)

    async def test_archive_notifies_users(self, service, tool_repo, bundle_repo, notification_repo):
        tool = make_tool()
        tool_repo.admin_get_by_id.return_value = tool
        bundle_repo.list_user_ids_with_tool.return_value = [5]

        await service.archive_tool(ADMIN, 1)

        tool_repo.archive.assert_awaited_once_with(tool)
        notification_repo.create_missing.assert_awaited_once_with(
            [5], NotificationType.TOOL_ARCHIVED, tool_id=1
        )

    async def test_archive_is_idempotent(self, service, tool_repo, notification_repo):
        tool_repo.admin_get_by_id.return_value = make_tool(archived=True)

        await service.archive_tool(ADMIN, 1)

        tool_repo.archive.assert_not_awaited()
        notification_repo.create_missing.assert_not_awaited()

    async def test_restore_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.restore_tool(USER, 1)

    async def test_restore_clears_notifications(self, service, tool_repo, notification_repo):
        tool = make_tool(archived=True)
        tool_repo.admin_get_by_id.return_value = tool

        await service.restore_tool(ADMIN, 1)

        tool_repo.restore.assert_awaited_once_with(tool)
        notification_repo.delete_for_item.assert_awaited_once_with(
            NotificationType.TOOL_ARCHIVED, tool_id=1
        )

    async def test_restore_active_tool_is_noop(self, service, tool_repo, notification_repo):
        tool_repo.admin_get_by_id.return_value = make_tool()

        await service.restore_tool(ADMIN, 1)

        tool_repo.restore.assert_not_awaited()
        notification_repo.delete_for_item.assert_not_awaited()


class TestCleanUrl:
    @pytest.mark.parametrize(
        "url",
        ["", "   ", None, "ftp://x.io", "file:///etc/passwd", "/relative/path",
         "x.io/path", "http://", "https://" + "a" * MAX_URL_LENGTH + ".io"],
    )
    def test_rejects_invalid(self, url):
        with pytest.raises(ValueError, match="absolute http"):
            ToolService._clean_url(url)

    @pytest.mark.parametrize("url", ["http://x.io", "https://x.io:8443/a?b=1"])
    def test_accepts_http_and_https(self, url):
        assert ToolService._clean_url(url) == url

    def test_strips_whitespace(self):
        assert ToolService._clean_url("  https://x.io ") == "https://x.io"