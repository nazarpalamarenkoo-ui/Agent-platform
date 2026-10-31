import pytest
import pytest_asyncio

from src.db.enums.notification_type import NotificationType
from src.db.enums.user_role import UserRole
from src.repositories.notification_repo import NotificationRepository
from src.repositories.skill_access_log_repo import SkillAccessLogRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.repositories.user_repo import UserRepository
from src.services.admin_user_content_service import AdminUserContentService, mask_url
from src.services.errors import ForbiddenError, NotFoundError


@pytest.fixture
def service(db_session):
    return AdminUserContentService(
        db_session,
        UserRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
        SkillAccessLogRepository(db_session),
        NotificationRepository(db_session),
    )


@pytest_asyncio.fixture
async def admin(make_user):
    return await make_user(role=UserRole.ADMIN)


@pytest_asyncio.fixture
async def super_admin(make_user):
    return await make_user(role=UserRole.SUPER_ADMIN)


class TestMaskUrl:
    def test_hides_query_string(self):
        assert mask_url("https://example.com/p?token=abc&x=1") == "https://example.com/p?***"

    def test_keeps_url_without_query_and_drops_fragment(self):
        assert mask_url("https://example.com/p#frag") == "https://example.com/p"

    def test_keeps_host_and_path(self):
        assert mask_url("http://h.io:8080/a/b?k=v") == "http://h.io:8080/a/b?***"


class TestAccessControl:
    async def test_regular_user_is_forbidden(self, service, sample_user, another_user):
        with pytest.raises(ForbiddenError, match="Admin access required"):
            await service.list_skills(sample_user, another_user.id)

    async def test_unknown_target_user(self, service, admin):
        with pytest.raises(NotFoundError, match="User not found"):
            await service.list_skills(admin, 999_999)

    async def test_admin_cannot_inspect_other_admin(self, service, admin, make_user):
        other = await make_user(role=UserRole.ADMIN)
        with pytest.raises(ForbiddenError, match="Only a super admin"):
            await service.overview(admin, other.id)

    async def test_super_admin_can_inspect_admin(self, service, super_admin, admin):
        overview = await service.overview(super_admin, admin.id)
        assert overview.user_id == admin.id

    async def test_admin_can_inspect_self(self, service, admin):
        overview = await service.overview(admin, admin.id)
        assert overview.user_id == admin.id


class TestListSkills:
    async def test_returns_only_target_private_skills_and_logs_access(
        self, service, admin, sample_user, another_user, make_skill
    ):
        mine = await make_skill(owner=sample_user)
        await make_skill(owner=another_user)

        skills = await service.list_skills(admin, sample_user.id)

        assert [s.id for s in skills] == [mine.id]

    async def test_archived_skills_only_with_flag(
        self, service, admin, sample_user, make_skill, db_session
    ):
        skill = await make_skill(owner=sample_user)
        await SkillRepository(db_session).archive(skill)

        assert await service.list_skills(admin, sample_user.id) == []
        flagged = await service.list_skills(admin, sample_user.id, include_archived=True)
        assert [s.id for s in flagged] == [skill.id]


class TestGetSkill:
    async def test_returns_target_skill(self, service, admin, sample_user, make_skill):
        skill = await make_skill(owner=sample_user)

        result = await service.get_skill(admin, sample_user.id, skill.id)

        assert result.id == skill.id

    async def test_raises_for_skill_of_other_user(
        self, service, admin, sample_user, another_user, make_skill
    ):
        foreign = await make_skill(owner=another_user)

        with pytest.raises(NotFoundError, match="Skill not found"):
            await service.get_skill(admin, sample_user.id, foreign.id)

    async def test_raises_for_global_skill(self, service, admin, sample_user, make_skill):
        global_skill = await make_skill()

        with pytest.raises(NotFoundError):
            await service.get_skill(admin, sample_user.id, global_skill.id)


class TestArchiveForViolation:
    async def test_archives_skill_and_notifies_owner(
        self, service, admin, sample_user, another_user, make_skill, db_session
    ):
        skill = await make_skill(owner=sample_user)

        result = await service.archive_for_violation(
            admin, sample_user.id, skill.id, "  spam content  "
        )

        assert result.archived_at is not None
        notifications = NotificationRepository(db_session)
        assert await notifications.count_unread(sample_user.id) == 1
        assert await notifications.count_unread(admin.id) == 0
        assert await notifications.count_unread(another_user.id) == 0

        rows = await notifications.list_for_user(
            sample_user.id, unread_only=False, limit=10, offset=0
        )
        assert rows[0][0].type == NotificationType.SKILL_ARCHIVED
        assert rows[0][0].skill_id == skill.id

    async def test_long_reason_is_accepted(
        self, service, admin, sample_user, make_skill
    ):
        skill = await make_skill(owner=sample_user)

        result = await service.archive_for_violation(
            admin, sample_user.id, skill.id, "r" * 1000
        )

        assert result.archived_at is not None

    async def test_regular_user_cannot_archive(
        self, service, sample_user, another_user, make_skill
    ):
        skill = await make_skill(owner=another_user)
        with pytest.raises(ForbiddenError):
            await service.archive_for_violation(sample_user, another_user.id, skill.id, "x")

    async def test_unknown_skill(self, service, admin, sample_user):
        with pytest.raises(NotFoundError):
            await service.archive_for_violation(admin, sample_user.id, 999_999, "x")


class TestListTools:
    async def test_masks_urls_and_scopes_to_target(
        self, service, admin, sample_user, another_user, make_tool
    ):
        mine = await make_tool(owner=sample_user, url="https://example.com/p?token=secret")
        await make_tool(owner=another_user)

        items = await service.list_tools(admin, sample_user.id)

        assert len(items) == 1
        assert items[0].id == mine.id
        assert items[0].url_masked == "https://example.com/p?***"
        assert "secret" not in items[0].url_masked

    async def test_archived_tools_only_with_flag(
        self, service, admin, sample_user, make_tool, db_session
    ):
        tool = await make_tool(owner=sample_user)
        await ToolDefinitionRepository(db_session).archive(tool)

        assert await service.list_tools(admin, sample_user.id) == []
        flagged = await service.list_tools(admin, sample_user.id, include_archived=True)
        assert [i.id for i in flagged] == [tool.id]
        assert flagged[0].archived_at is not None


class TestOverview:
    async def test_counts_active_content_and_usage(
        self,
        service,
        admin,
        sample_user,
        sample_agent_profile,
        make_skill,
        make_tool,
        make_bundle,
        sample_token_usage_event,
        db_session,
    ):
        await make_skill(owner=sample_user)
        archived = await make_skill(owner=sample_user)
        await SkillRepository(db_session).archive(archived)
        await make_tool(owner=sample_user)
        await make_bundle(sample_user, sample_agent_profile)

        overview = await service.overview(admin, sample_user.id)

        assert overview.private_skills == 1
        assert overview.private_tools == 1
        assert overview.bundles == 1
        assert overview.token_events == 1
        assert overview.tokens_used == sample_user.tokens_used
        assert overview.token_limit == sample_user.token_limit

    async def test_zero_counts_for_empty_user(self, service, admin, sample_user):
        overview = await service.overview(admin, sample_user.id)

        assert overview.private_skills == 0
        assert overview.private_tools == 0
        assert overview.bundles == 0
        assert overview.token_events == 0