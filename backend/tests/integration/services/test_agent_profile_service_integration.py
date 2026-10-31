import pytest
import pytest_asyncio

from src.db.enums.user_role import UserRole
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.agent_profile_service import UNAVAILABLE, AgentProfileService
from src.services.errors import ConflictError, ForbiddenError, NotFoundError


@pytest.fixture
def service(db_session):
    return AgentProfileService(
        AgentProfileRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
    )


@pytest_asyncio.fixture
async def admin(make_user):
    return await make_user(role=UserRole.ADMIN)


class TestCreateProfile:
    async def test_persists_profile_with_skill_and_tool_links(
        self, service, admin, sample_skill, sample_tool
    ):
        profile = await service.create_profile(
            admin,
            "  research-agent ",
            "Looks things up",
            skill_ids=[sample_skill.id, sample_skill.id],
            tool_ids=[sample_tool.id],
        )

        reloaded = await service.get_profile(admin, profile.id)
        assert reloaded.agent_name == "research-agent"
        assert [s.id for s in reloaded.skills] == [sample_skill.id]
        assert [t.id for t in reloaded.tools] == [sample_tool.id]
        assert reloaded.is_neutral is False

    async def test_forbidden_for_regular_user(self, service, sample_user):
        with pytest.raises(ForbiddenError):
            await service.create_profile(sample_user, "n", "d")

    async def test_raises_for_empty_name(self, service, admin):
        with pytest.raises(ValueError, match="Profile name must not be empty"):
            await service.create_profile(admin, "  ", "d")

    async def test_raises_on_duplicate_name(self, service, admin):
        await service.create_profile(admin, "dup", "d")

        with pytest.raises(ConflictError, match="Profile 'dup' already exists"):
            await service.create_profile(admin, "dup", "d2")

    async def test_only_one_neutral_profile_allowed(self, service, admin):
        await service.create_profile(admin, "neutral-1", "d", is_neutral=True)

        with pytest.raises(ConflictError, match="neutral profile already exists"):
            await service.create_profile(admin, "neutral-2", "d", is_neutral=True)

    async def test_raises_for_unknown_skill_and_creates_nothing(
        self, service, admin, sample_tool, db_session
    ):
        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_profile(
                admin, "broken", "d", skill_ids=[999_999], tool_ids=[sample_tool.id]
            )

        assert await AgentProfileRepository(db_session).admin_get_by_name("broken") is None

    async def test_raises_for_unknown_tool(self, service, admin, sample_skill):
        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_profile(
                admin, "broken-2", "d", skill_ids=[sample_skill.id], tool_ids=[999_999]
            )

    async def test_private_skill_is_unavailable(
        self, service, admin, sample_user, make_skill
    ):
        private = await make_skill(owner=sample_user)
        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_profile(admin, "p", "d", skill_ids=[private.id])

    async def test_private_tool_is_unavailable(self, service, admin, sample_user, make_tool):
        private = await make_tool(owner=sample_user)
        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_profile(admin, "p2", "d", tool_ids=[private.id])


class TestUpdateProfile:
    async def test_updates_description(self, service, admin, sample_agent_profile):
        updated = await service.update_profile(
            admin, sample_agent_profile.id, description="new description"
        )
        assert updated.description == "new description"

    async def test_syncs_skills_adds_and_removes(
        self, service, admin, make_skill
    ):
        s1, s2, s3 = await make_skill(), await make_skill(), await make_skill()
        profile = await service.create_profile(admin, "sync", "d", skill_ids=[s1.id, s2.id])

        updated = await service.update_profile(admin, profile.id, skill_ids=[s2.id, s3.id])

        assert {s.id for s in updated.skills} == {s2.id, s3.id}

    async def test_syncs_tools_adds_and_removes(self, service, admin, make_tool):
        t1, t2 = await make_tool(), await make_tool()
        profile = await service.create_profile(admin, "sync-t", "d", tool_ids=[t1.id])

        updated = await service.update_profile(admin, profile.id, tool_ids=[t2.id])

        assert [t.id for t in updated.tools] == [t2.id]

    async def test_empty_list_removes_everything(self, service, admin, sample_skill):
        profile = await service.create_profile(admin, "clear", "d", skill_ids=[sample_skill.id])

        updated = await service.update_profile(admin, profile.id, skill_ids=[])

        assert updated.skills == []

    async def test_none_leaves_relations_untouched(self, service, admin, sample_skill):
        profile = await service.create_profile(admin, "keep", "d", skill_ids=[sample_skill.id])

        updated = await service.update_profile(admin, profile.id, description="x")

        assert [s.id for s in updated.skills] == [sample_skill.id]

    async def test_invalid_tool_ids_do_not_change_skills(
        self, service, admin, make_skill
    ):
        s1, s2 = await make_skill(), await make_skill()
        profile = await service.create_profile(admin, "atomic", "d", skill_ids=[s1.id])

        with pytest.raises(NotFoundError):
            await service.update_profile(
                admin, profile.id, skill_ids=[s2.id], tool_ids=[999_999]
            )

        reloaded = await service.get_profile(admin, profile.id)
        assert [s.id for s in reloaded.skills] == [s1.id]

    async def test_forbidden_for_regular_user(self, service, sample_user, sample_agent_profile):
        with pytest.raises(ForbiddenError):
            await service.update_profile(sample_user, sample_agent_profile.id, description="x")

    async def test_unknown_profile(self, service, admin):
        with pytest.raises(NotFoundError, match="Agent profile not found"):
            await service.update_profile(admin, 999_999, description="x")


class TestArchiveAndRestore:
    async def test_archive_hides_profile_from_regular_users(
        self, service, admin, sample_user, sample_agent_profile
    ):
        archived = await service.archive_profile(admin, sample_agent_profile.id)

        assert archived.archived_at is not None
        with pytest.raises(NotFoundError):
            await service.get_profile(sample_user, sample_agent_profile.id)
        assert (await service.get_profile(admin, sample_agent_profile.id)).id == sample_agent_profile.id

    async def test_neutral_profile_cannot_be_archived(self, service, admin):
        neutral = await service.create_profile(admin, "neutral", "d", is_neutral=True)

        with pytest.raises(ConflictError, match="neutral profile cannot be archived"):
            await service.archive_profile(admin, neutral.id)

    async def test_restore_makes_profile_visible_again(
        self, service, admin, sample_user, sample_agent_profile
    ):
        await service.archive_profile(admin, sample_agent_profile.id)

        restored = await service.restore_profile(admin, sample_agent_profile.id)

        assert restored.archived_at is None
        assert (await service.get_profile(sample_user, sample_agent_profile.id)).id == sample_agent_profile.id

    async def test_forbidden_for_regular_user(self, service, sample_user, sample_agent_profile):
        with pytest.raises(ForbiddenError):
            await service.archive_profile(sample_user, sample_agent_profile.id)
        with pytest.raises(ForbiddenError):
            await service.restore_profile(sample_user, sample_agent_profile.id)


class TestListProfiles:
    async def test_lists_active_profiles(
        self, service, sample_user, sample_agent_profile, another_agent_profile
    ):
        ids = {p.id for p in await service.list_profiles(sample_user)}
        assert {sample_agent_profile.id, another_agent_profile.id} <= ids

    async def test_archived_hidden_by_default_and_visible_for_admin_with_flag(
        self, service, admin, sample_agent_profile
    ):
        await service.archive_profile(admin, sample_agent_profile.id)

        default = {p.id for p in await service.list_profiles(admin)}
        flagged = {p.id for p in await service.list_profiles(admin, include_archived=True)}

        assert sample_agent_profile.id not in default
        assert sample_agent_profile.id in flagged

    async def test_include_archived_requires_admin(self, service, sample_user):
        with pytest.raises(ForbiddenError):
            await service.list_profiles(sample_user, include_archived=True)

    async def test_respects_limit_and_offset(
        self, service, sample_user, sample_agent_profile, another_agent_profile
    ):
        first = await service.list_profiles(sample_user, limit=1, offset=0)
        second = await service.list_profiles(sample_user, limit=1, offset=1)

        assert len(first) == len(second) == 1
        assert first[0].id != second[0].id


class TestGetProfile:
    async def test_raises_for_unknown_id(self, service, sample_user):
        with pytest.raises(NotFoundError, match="Agent profile not found"):
            await service.get_profile(sample_user, 999_999)