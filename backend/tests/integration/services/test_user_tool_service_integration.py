import pytest

from src.db.enums.tool_auth_type import ToolAuthType
from src.db.enums.tool_visibility import ToolVisibility
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.errors import ConflictError, NotFoundError
from src.services.user_tool_service import (
    MAX_DESCRIPTION,
    MAX_NAME,
    UserToolService,
    inspect_url,
)

URL = "https://example.com/tool"


@pytest.fixture
def service(db_session):
    return UserToolService(
        ToolDefinitionRepository(db_session),
        KnowledgeDomainRepository(db_session),
        max_private_tools=2,
        allow_private_hosts=False,
    )


class TestInspectUrl:
    def test_accepts_plain_https_url(self):
        url, warnings = inspect_url("  https://example.com/a  ", False)
        assert url == "https://example.com/a"
        assert warnings == []

    @pytest.mark.parametrize(
        "bad",
        ["", "ftp://example.com", "example.com", "https://", "https://exa mple.com",
         "https://example.com:notaport", "https://user:pw@example.com"],
    )
    def test_rejects_malformed_urls(self, bad):
        with pytest.raises(ValueError):
            inspect_url(bad, False)

    @pytest.mark.parametrize(
        "private",
        ["http://localhost/x", "http://127.0.0.1/x", "http://10.0.0.5/x",
         "http://192.168.1.1/x", "http://169.254.1.1/x", "http://printer.local/x"],
    )
    def test_blocks_private_hosts_when_not_allowed(self, private):
        with pytest.raises(ValueError, match="Local and private addresses"):
            inspect_url(private, False)

    def test_allows_private_hosts_when_enabled(self):
        url, _ = inspect_url("http://10.0.0.5/x", True)
        assert url == "http://10.0.0.5/x"

    def test_warns_about_sensitive_query_params(self):
        _, warnings = inspect_url("https://example.com/x?token=1&API_KEY=2&q=ok", False)

        assert any("credential-like" in w and "token" in w and "API_KEY".lower() in w.lower()
                   for w in warnings)

    def test_warns_about_plain_http(self):
        _, warnings = inspect_url("http://example.com/x", False)
        assert any("plain http" in w for w in warnings)

    def test_no_http_warning_for_localhost_when_allowed(self):
        _, warnings = inspect_url("http://localhost:8000/x", True)
        assert not any("plain http" in w for w in warnings)


class TestCreateTool:
    async def test_persists_private_tool_owned_by_actor(
        self, service, sample_user, sample_knowledge_domain
    ):
        tool, warnings = await service.create_tool(
            sample_user,
            " my-tool ",
            "  some \n description ",
            URL,
            auth_type=ToolAuthType.NONE,
            domain_ids=[sample_knowledge_domain.id],
        )

        assert tool.tool_name == "my-tool"
        assert tool.description == "some description"
        assert tool.visibility == ToolVisibility.PRIVATE
        assert tool.owner_id == sample_user.id
        assert [d.id for d in tool.domains] == [sample_knowledge_domain.id]
        assert warnings == []

    async def test_returns_warnings_for_leaky_url(self, service, sample_user):
        tool, warnings = await service.create_tool(
            sample_user, "leaky", "d", "https://example.com/x?api_key=abc"
        )

        assert tool.id is not None
        assert warnings

    async def test_rejects_private_host(self, service, sample_user):
        with pytest.raises(ValueError, match="Local and private"):
            await service.create_tool(sample_user, "local", "d", "http://localhost/x")

    async def test_validates_name_and_description(self, service, sample_user):
        with pytest.raises(ValueError, match="name must not be empty"):
            await service.create_tool(sample_user, " ", "d", URL)
        with pytest.raises(ValueError, match=str(MAX_NAME)):
            await service.create_tool(sample_user, "x" * (MAX_NAME + 1), "d", URL)
        with pytest.raises(ValueError, match="description must not be empty"):
            await service.create_tool(sample_user, "n", " ", URL)
        with pytest.raises(ValueError, match=str(MAX_DESCRIPTION)):
            await service.create_tool(sample_user, "n", "d" * (MAX_DESCRIPTION + 1), URL)

    async def test_raises_on_duplicate_name_for_same_owner(self, service, sample_user):
        await service.create_tool(sample_user, "dup", "d", URL)

        with pytest.raises(ConflictError, match="already have a tool named 'dup'"):
            await service.create_tool(sample_user, "dup", "d", URL)

    async def test_same_name_allowed_for_different_owners(
        self, service, sample_user, another_user
    ):
        await service.create_tool(sample_user, "same", "d", URL)
        tool, _ = await service.create_tool(another_user, "same", "d", URL)

        assert tool.owner_id == another_user.id

    async def test_enforces_quota(self, service, sample_user):
        await service.create_tool(sample_user, "t1", "d", URL)
        await service.create_tool(sample_user, "t2", "d", URL)

        with pytest.raises(ConflictError, match="at most 2 active private tools"):
            await service.create_tool(sample_user, "t3", "d", URL)

    async def test_raises_for_missing_domain(self, service, sample_user):
        with pytest.raises(NotFoundError, match="Domain 999999 not found"):
            await service.create_tool(sample_user, "n", "d", URL, domain_ids=[999_999])


class TestUpdateTool:
    async def test_updates_fields(self, service, sample_user):
        tool, _ = await service.create_tool(sample_user, "upd", "old", URL)

        updated, warnings = await service.update_tool(
            sample_user,
            tool.id,
            description="new",
            url="https://example.com/new",
            auth_description="key in header",
        )

        assert updated.description == "new"
        assert updated.url == "https://example.com/new"
        assert updated.auth_description == "key in header"
        assert warnings == []

    async def test_warns_when_new_url_leaks_credentials(self, service, sample_user):
        tool, _ = await service.create_tool(sample_user, "upd2", "d", URL)

        _, warnings = await service.update_tool(
            sample_user, tool.id, url="https://example.com/x?secret=1"
        )

        assert warnings

    async def test_rejects_invalid_url_and_keeps_old(self, service, sample_user):
        tool, _ = await service.create_tool(sample_user, "upd3", "d", URL)

        with pytest.raises(ValueError):
            await service.update_tool(sample_user, tool.id, url="ftp://bad")

        assert (await service.get_tool(sample_user, tool.id)).url == URL

    async def test_cannot_update_foreign_tool(self, service, sample_user, another_user):
        tool, _ = await service.create_tool(another_user, "theirs", "d", URL)

        with pytest.raises(NotFoundError):
            await service.update_tool(sample_user, tool.id, description="x")


class TestArchiveAndRestore:
    async def test_archive_frees_quota_restore_consumes_it(self, service, sample_user):
        first, _ = await service.create_tool(sample_user, "t1", "d", URL)
        await service.create_tool(sample_user, "t2", "d", URL)

        archived = await service.archive_tool(sample_user, first.id)
        assert archived.archived_at is not None

        await service.create_tool(sample_user, "t3", "d", URL)

        with pytest.raises(ConflictError, match="at most 2"):
            await service.restore_tool(sample_user, first.id)

    async def test_restore_clears_archived_at(self, service, sample_user):
        tool, _ = await service.create_tool(sample_user, "r", "d", URL)
        await service.archive_tool(sample_user, tool.id)

        restored = await service.restore_tool(sample_user, tool.id)

        assert restored.archived_at is None


class TestListAndGet:
    async def test_lists_only_own_tools(self, service, sample_user, another_user):
        mine, _ = await service.create_tool(sample_user, "mine", "d", URL)
        theirs, _ = await service.create_tool(another_user, "theirs", "d", URL)

        ids = {t.id for t in await service.list_tools(sample_user)}

        assert mine.id in ids
        assert theirs.id not in ids

    async def test_archived_hidden_unless_requested(self, service, sample_user):
        tool, _ = await service.create_tool(sample_user, "arch", "d", URL)
        await service.archive_tool(sample_user, tool.id)

        default = {t.id for t in await service.list_tools(sample_user)}
        with_archived = {
            t.id for t in await service.list_tools(sample_user, include_archived=True)
        }

        assert tool.id not in default
        assert tool.id in with_archived

    async def test_get_tool_raises_for_foreign_or_unknown(
        self, service, sample_user, another_user
    ):
        theirs, _ = await service.create_tool(another_user, "theirs", "d", URL)

        with pytest.raises(NotFoundError, match="Tool not found"):
            await service.get_tool(sample_user, theirs.id)
        with pytest.raises(NotFoundError):
            await service.get_tool(sample_user, 999_999)