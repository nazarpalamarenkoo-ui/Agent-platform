from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.db.enums.tool_auth_type import ToolAuthType
from src.db.enums.tool_visibility import ToolVisibility
from src.services import user_tool_service as mod
from src.services.errors import ConflictError, NotFoundError
from src.services.user_tool_service import (
    MAX_DESCRIPTION,
    MAX_NAME,
    UserToolService,
    inspect_url,
)

ACTOR = SimpleNamespace(id=5)
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_tool(id=1, archived=False):
    return SimpleNamespace(id=id, archived_at=NOW if archived else None)


class TestInspectUrl:
    @pytest.mark.parametrize(
        "url",
        ["", "   ", None, "ftp://x.io", "x.io/path", "https://", "https://exa mple.com",
         "https://" + "a" * 2050],
    )
    def test_rejects_malformed(self, url):
        with pytest.raises(ValueError, match="absolute http"):
            inspect_url(url, allow_private_hosts=True)

    @pytest.mark.parametrize("url", ["https://x.io:99999", "https://x.io:abc"])
    def test_rejects_invalid_port(self, url):
        with pytest.raises(ValueError, match="invalid port"):
            inspect_url(url, allow_private_hosts=True)

    def test_rejects_credentials_in_url(self):
        with pytest.raises(ValueError, match="login or password"):
            inspect_url("https://user:pw@x.io", allow_private_hosts=True)

    def test_returns_stripped_url_without_warnings_for_clean_https(self):
        assert inspect_url("  https://api.x.io/v1 ", True) == ("https://api.x.io/v1", [])

    @pytest.mark.parametrize(
        "url",
        ["http://localhost:8000", "http://LOCALHOST", "http://svc.local/x", "http://127.0.0.1",
         "http://10.0.0.5", "http://192.168.1.1", "http://172.16.0.1",
         "http://169.254.169.254/latest/meta-data", "http://[::1]/"],
    )
    def test_blocks_private_hosts_when_disallowed(self, url):
        with pytest.raises(ValueError, match="Local and private addresses"):
            inspect_url(url, allow_private_hosts=False)

    def test_allows_private_hosts_when_enabled(self):
        url, _ = inspect_url("https://10.0.0.5/api", allow_private_hosts=True)

        assert url == "https://10.0.0.5/api"

    def test_allows_public_ip_when_disallowed(self):
        assert inspect_url("https://8.8.8.8/x", False)[0] == "https://8.8.8.8/x"

    @pytest.mark.xfail(reason="integer-form IPs are not recognised as private", strict=False)
    def test_blocks_decimal_encoded_loopback(self):
        with pytest.raises(ValueError):
            inspect_url("http://2130706433/", allow_private_hosts=False)

    def test_warns_about_credential_like_params(self):
        _, warnings = inspect_url("https://x.io/a?API_KEY=1&token=2&q=3", True)

        assert len(warnings) == 1
        assert "API_KEY, token" in warnings[0]

    def test_warns_about_plain_http(self):
        _, warnings = inspect_url("http://x.io", True)

        assert warnings == ["The URL uses plain http: traffic is not encrypted."]

    def test_no_http_warning_for_localhost(self):
        assert inspect_url("http://localhost:8000", True)[1] == []

    def test_collects_both_warnings(self):
        _, warnings = inspect_url("http://x.io/?token=1", True)

        assert len(warnings) == 2


@pytest.fixture
def tool_repo():
    repo = AsyncMock()
    repo.get_owned_by_name.return_value = None
    repo.count_owned_active.return_value = 0
    return repo


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def service(tool_repo, domain_repo):
    return UserToolService(tool_repo, domain_repo, max_private_tools=2, allow_private_hosts=False)


class TestInit:
    def test_reads_flag_from_settings_when_not_given(self, monkeypatch, tool_repo, domain_repo):
        monkeypatch.setattr(mod, "settings", SimpleNamespace(ALLOW_PRIVATE_TOOL_HOSTS=False))

        assert UserToolService(tool_repo, domain_repo).allow_private_hosts is False

    def test_defaults_to_allowed_when_setting_is_missing(self, monkeypatch, tool_repo, domain_repo):
        monkeypatch.setattr(mod, "settings", SimpleNamespace())

        assert UserToolService(tool_repo, domain_repo).allow_private_hosts is True

    def test_explicit_flag_overrides_settings(self, monkeypatch, tool_repo, domain_repo):
        monkeypatch.setattr(mod, "settings", SimpleNamespace(ALLOW_PRIVATE_TOOL_HOSTS=False))

        assert UserToolService(tool_repo, domain_repo, allow_private_hosts=True).allow_private_hosts is True


class TestGetAndList:
    async def test_list_delegates(self, service, tool_repo):
        await service.list_tools(ACTOR, limit=5, offset=1, include_archived=True)

        tool_repo.list_owned.assert_awaited_once_with(5, limit=5, offset=1, include_archived=True)

    async def test_get_not_found(self, service, tool_repo):
        tool_repo.get_owned_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Tool not found"):
            await service.get_tool(ACTOR, 1)


class TestCreateTool:
    async def test_creates_private_tool_and_returns_warnings(self, service, tool_repo, domain_repo):
        created = make_tool(id=9)
        tool_repo.create.return_value = created
        tool_repo.get_owned_by_id.return_value = created
        domain = SimpleNamespace(id=1)
        domain_repo.get_by_id.return_value = domain

        tool, warnings = await service.create_tool(
            ACTOR, " name ", " a   b ", "http://x.io", auth_description="ad", domain_ids=[1, 1]
        )

        assert tool is created
        assert len(warnings) == 1
        tool_repo.create.assert_awaited_once_with(
            tool_name="name", description="a b", url="http://x.io",
            auth_type=ToolAuthType.NONE, auth_description="ad",
            visibility=ToolVisibility.PRIVATE, owner_id=5,
        )
        tool_repo.add_domain.assert_awaited_once_with(created, domain)

    async def test_blocks_private_host_by_policy(self, service, tool_repo):
        with pytest.raises(ValueError, match="Local and private"):
            await service.create_tool(ACTOR, "n", "d", "http://127.0.0.1/")

        tool_repo.create.assert_not_awaited()

    @pytest.mark.parametrize("name", ["", None])
    async def test_rejects_empty_name(self, service, name):
        with pytest.raises(ValueError, match="Tool name must not be empty"):
            await service.create_tool(ACTOR, name, "d", "https://x.io")

    async def test_rejects_too_long_name(self, service):
        with pytest.raises(ValueError, match="must not exceed"):
            await service.create_tool(ACTOR, "n" * (MAX_NAME + 1), "d", "https://x.io")

    async def test_rejects_empty_and_too_long_description(self, service):
        with pytest.raises(ValueError, match="description must not be empty"):
            await service.create_tool(ACTOR, "n", "  ", "https://x.io")
        with pytest.raises(ValueError, match="description must not exceed"):
            await service.create_tool(ACTOR, "n", "d" * (MAX_DESCRIPTION + 1), "https://x.io")

    async def test_rejects_duplicate_name(self, service, tool_repo):
        tool_repo.get_owned_by_name.return_value = make_tool()

        with pytest.raises(ConflictError, match="already have a tool named 'n'"):
            await service.create_tool(ACTOR, "n", "d", "https://x.io")

    async def test_rejects_when_quota_reached(self, service, tool_repo):
        tool_repo.count_owned_active.return_value = 2

        with pytest.raises(ConflictError, match="at most 2 active private tools"):
            await service.create_tool(ACTOR, "n", "d", "https://x.io")

        tool_repo.create.assert_not_awaited()

    async def test_missing_domain(self, service, tool_repo, domain_repo):
        domain_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Domain 4 not found"):
            await service.create_tool(ACTOR, "n", "d", "https://x.io", domain_ids=[4])

        tool_repo.create.assert_not_awaited()


class TestUpdateTool:
    @pytest.fixture
    def tool(self, tool_repo):
        t = make_tool()
        tool_repo.get_owned_by_id.return_value = t
        return t

    async def test_updates_fields_and_returns_url_warnings(self, service, tool_repo, tool):
        _, warnings = await service.update_tool(
            ACTOR, 1, description=" new  d ", url="http://x.io", auth_type=ToolAuthType.NONE,
            auth_description="ad",
        )

        tool_repo.update.assert_awaited_once_with(
            tool, description="new d", url="http://x.io",
            auth_type=ToolAuthType.NONE, auth_description="ad",
        )
        assert len(warnings) == 1

    async def test_no_changes_no_update(self, service, tool_repo, tool):
        _, warnings = await service.update_tool(ACTOR, 1)

        tool_repo.update.assert_not_awaited()
        assert warnings == []

    async def test_invalid_url_rejected(self, service, tool_repo, tool):
        with pytest.raises(ValueError):
            await service.update_tool(ACTOR, 1, url="http://localhost")

        tool_repo.update.assert_not_awaited()

    async def test_not_found(self, service, tool_repo):
        tool_repo.get_owned_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.update_tool(ACTOR, 1, description="d")


class TestArchiveRestore:
    async def test_archive(self, service, tool_repo):
        tool = make_tool()
        tool_repo.get_owned_by_id.return_value = tool

        await service.archive_tool(ACTOR, 1)

        tool_repo.archive.assert_awaited_once_with(tool)

    async def test_restore_checks_quota(self, service, tool_repo):
        tool = make_tool(archived=True)
        tool_repo.get_owned_by_id.return_value = tool
        tool_repo.count_owned_active.return_value = 2

        with pytest.raises(ConflictError):
            await service.restore_tool(ACTOR, 1)

        tool_repo.restore.assert_not_awaited()

    async def test_restore_archived_tool(self, service, tool_repo):
        tool = make_tool(archived=True)
        tool_repo.get_owned_by_id.return_value = tool

        await service.restore_tool(ACTOR, 1)

        tool_repo.restore.assert_awaited_once_with(tool)

    async def test_restore_active_tool_is_noop(self, service, tool_repo):
        tool_repo.get_owned_by_id.return_value = make_tool()
        tool_repo.count_owned_active.return_value = 2

        await service.restore_tool(ACTOR, 1)

        tool_repo.restore.assert_not_awaited()