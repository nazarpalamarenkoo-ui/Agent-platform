import pytest
import pytest_asyncio

from src.db.enums.tool_auth_type import ToolAuthType
from src.db.enums.tool_visibility import ToolVisibility
from src.db.enums.user_role import UserRole
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.notification_repo import NotificationRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.tool_service import ToolService

URL = "https://example.com/api"


@pytest.fixture
def service(db_session):
    return ToolService(
        ToolDefinitionRepository(db_session),
        KnowledgeDomainRepository(db_session),
        ConfigBundleRepository(db_session),
        NotificationRepository(db_session),
    )


@pytest_asyncio.fixture
async def admin(make_user):
    return await make_user(role=UserRole.ADMIN)


class TestCreateTool:
    async def test_persists_global_tool_with_domains(
        self, service, admin, sample_knowledge_domain
    ):
        tool = await service.create_tool(
            admin,
            "  web-search  ",
            "Searches the web",
            URL,
            auth_type=ToolAuthType.NONE,
            domain_ids=[sample_knowledge_domain.id],
        )

        assert tool.id is not None
        assert tool.tool_name == "web-search"
        assert tool.visibility == ToolVisibility.GLOBAL
        assert tool.owner_id is None
        assert [d.id for d in tool.domains] == [sample_knowledge_domain.id]

    async def test_forbidden_for_regular_user(self, service, sample_user):
        with pytest.raises(ForbiddenError):
            await service.create_tool(sample_user, "t", "d", URL)

    async def test_raises_for_empty_name(self, service, admin):
        with pytest.raises(ValueError, match="Tool name must not be empty"):
            await service.create_tool(admin, "  ", "d", URL)

    @pytest.mark.parametrize(
        "bad_url", ["", "ftp://example.com", "not-a-url", "https://", "x" * 3000]
    )
    async def test_rejects_invalid_urls(self, service, admin, bad_url):
        with pytest.raises(ValueError, match="absolute http\\(s\\) URL"):
            await service.create_tool(admin, "bad-url", "d", bad_url)

    async def test_raises_on_duplicate_name(self, service, admin):
        await service.create_tool(admin, "dup", "d", URL)

        with pytest.raises(ConflictError, match="Tool 'dup' already exists"):
            await service.create_tool(admin, "dup", "d2", URL)

    async def test_raises_when_domain_missing_and_creates_nothing(
        self, service, admin, db_session
    ):
        with pytest.raises(NotFoundError, match="Domain 999999 not found"):
            await service.create_tool(admin, "orphan", "d", URL, domain_ids=[999_999])

        assert await ToolDefinitionRepository(db_session).get_global_by_name("orphan") is None


class TestUpdateTool:
    async def test_updates_all_provided_fields(self, service, admin):
        tool = await service.create_tool(admin, "upd", "old", URL)

        updated = await service.update_tool(
            admin,
            tool.id,
            description="new",
            url="https://example.com/new",
            auth_type=ToolAuthType(list(ToolAuthType)[-1]),
            auth_description="needs key",
        )

        assert updated.description == "new"
        assert updated.url == "https://example.com/new"
        assert updated.auth_description == "needs key"

    async def test_rejects_invalid_url(self, service, admin):
        tool = await service.create_tool(admin, "upd-bad", "d", URL)

        with pytest.raises(ValueError):
            await service.update_tool(admin, tool.id, url="ftp://x")

    async def test_raises_for_private_tool(self, service, admin, sample_user, make_tool):
        private = await make_tool(owner=sample_user)
        with pytest.raises(NotFoundError):
            await service.update_tool(admin, private.id, description="x")

    async def test_forbidden_for_regular_user(self, service, sample_user, make_tool):
        tool = await make_tool()
        with pytest.raises(ForbiddenError):
            await service.update_tool(sample_user, tool.id, description="x")


class TestArchiveAndRestore:
    async def test_archive_marks_tool_and_notifies_bundle_owners(
        self, service, admin, db_session, sample_user, another_user,
        sample_agent_profile, make_bundle, make_tool,
    ):
        tool = await make_tool()
        bundle = await make_bundle(sample_user, sample_agent_profile)
        await ConfigBundleRepository(db_session).add_tool(bundle, tool)

        archived = await service.archive_tool(admin, tool.id)

        assert archived.archived_at is not None
        notifications = NotificationRepository(db_session)
        assert await notifications.count_unread(sample_user.id) == 1
        assert await notifications.count_unread(another_user.id) == 0

    async def test_archive_twice_does_not_duplicate_notifications(
        self, service, admin, db_session, sample_user, sample_agent_profile,
        make_bundle, make_tool,
    ):
        tool = await make_tool()
        bundle = await make_bundle(sample_user, sample_agent_profile)
        await ConfigBundleRepository(db_session).add_tool(bundle, tool)

        await service.archive_tool(admin, tool.id)
        await service.archive_tool(admin, tool.id)

        assert await NotificationRepository(db_session).count_unread(sample_user.id) == 1

    async def test_restore_clears_archive_and_notifications(
        self, service, admin, db_session, sample_user, sample_agent_profile,
        make_bundle, make_tool,
    ):
        tool = await make_tool()
        bundle = await make_bundle(sample_user, sample_agent_profile)
        await ConfigBundleRepository(db_session).add_tool(bundle, tool)
        await service.archive_tool(admin, tool.id)

        restored = await service.restore_tool(admin, tool.id)

        assert restored.archived_at is None
        assert await NotificationRepository(db_session).count_unread(sample_user.id) == 0

    async def test_archive_forbidden_for_regular_user(
        self, service, sample_user, make_tool
    ):
        tool = await make_tool()
        with pytest.raises(ForbiddenError):
            await service.archive_tool(sample_user, tool.id)


class TestListTools:
    async def test_user_sees_global_and_own_private_only(
        self, service, sample_user, another_user, make_tool
    ):
        global_tool = await make_tool()
        own = await make_tool(owner=sample_user)
        foreign = await make_tool(owner=another_user)

        ids = {t.id for t in await service.list_tools(sample_user)}

        assert global_tool.id in ids
        assert own.id in ids
        assert foreign.id not in ids

    async def test_include_archived_requires_admin(self, service, sample_user):
        with pytest.raises(ForbiddenError):
            await service.list_tools(sample_user, include_archived=True)

    async def test_admin_include_archived(self, service, admin, make_tool):
        tool = await make_tool()
        await service.archive_tool(admin, tool.id)

        visible = {t.id for t in await service.list_tools(admin)}
        with_archived = {
            t.id for t in await service.list_tools(admin, include_archived=True)
        }

        assert tool.id not in visible
        assert tool.id in with_archived

    async def test_filters_by_domain(
        self, service, admin, sample_knowledge_domain, another_knowledge_domain
    ):
        a = await service.create_tool(
            admin, "in-a", "d", URL, domain_ids=[sample_knowledge_domain.id]
        )
        b = await service.create_tool(
            admin, "in-b", "d", URL, domain_ids=[another_knowledge_domain.id]
        )

        ids = {
            t.id
            for t in await service.list_tools(admin, domain_id=sample_knowledge_domain.id)
        }

        assert a.id in ids
        assert b.id not in ids


class TestGetTool:
    async def test_returns_global_tool(self, service, sample_user, make_tool):
        tool = await make_tool()
        assert (await service.get_tool(sample_user, tool.id)).id == tool.id

    async def test_hides_foreign_private_tool_even_from_admin(
        self, service, admin, another_user, make_tool
    ):
        foreign = await make_tool(owner=another_user)
        with pytest.raises(NotFoundError):
            await service.get_tool(admin, foreign.id)

    async def test_admin_can_read_archived_global_tool(self, service, admin, make_tool):
        tool = await make_tool()
        await service.archive_tool(admin, tool.id)

        assert (await service.get_tool(admin, tool.id)).id == tool.id

    async def test_raises_for_unknown_id(self, service, sample_user):
        with pytest.raises(NotFoundError, match="Tool not found"):
            await service.get_tool(sample_user, 999_999)