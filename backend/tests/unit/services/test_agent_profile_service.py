from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.agent_profile_service import UNAVAILABLE, AgentProfileService
from src.services.errors import ConflictError, ForbiddenError, NotFoundError

ADMIN = SimpleNamespace(id=1, is_admin=True)
USER = SimpleNamespace(id=2, is_admin=False)


def obj(id):
    return SimpleNamespace(id=id)


@pytest.fixture
def agent_repo():
    repo = AsyncMock()
    repo.admin_get_by_name.return_value = None
    repo.get_neutral.return_value = None
    return repo


@pytest.fixture
def skill_repo():
    return AsyncMock()


@pytest.fixture
def tool_repo():
    return AsyncMock()


@pytest.fixture
def service(agent_repo, skill_repo, tool_repo):
    return AgentProfileService(agent_repo, skill_repo, tool_repo)


class TestListProfiles:
    async def test_regular_listing_uses_active(self, service, agent_repo):
        agent_repo.list_active.return_value = [obj(1)]

        result = await service.list_profiles(USER, limit=5, offset=10)

        assert result == [obj(1)]
        agent_repo.list_active.assert_awaited_once_with(limit=5, offset=10)

    async def test_include_archived_requires_admin(self, service, agent_repo):
        with pytest.raises(ForbiddenError):
            await service.list_profiles(USER, include_archived=True)

        agent_repo.admin_list.assert_not_awaited()

    async def test_admin_can_include_archived(self, service, agent_repo):
        await service.list_profiles(ADMIN, include_archived=True)

        agent_repo.admin_list.assert_awaited_once_with(limit=100, offset=0, include_archived=True)


class TestGetProfile:
    async def test_returns_active_profile(self, service, agent_repo):
        profile = obj(1)
        agent_repo.get_active.return_value = profile

        assert await service.get_profile(USER, 1) is profile
        agent_repo.admin_get_by_id.assert_not_awaited()

    async def test_admin_falls_back_to_archived(self, service, agent_repo):
        archived = obj(1)
        agent_repo.get_active.return_value = None
        agent_repo.admin_get_by_id.return_value = archived

        assert await service.get_profile(ADMIN, 1) is archived

    async def test_regular_user_cannot_see_archived(self, service, agent_repo):
        agent_repo.get_active.return_value = None

        with pytest.raises(NotFoundError, match="Agent profile not found"):
            await service.get_profile(USER, 1)

        agent_repo.admin_get_by_id.assert_not_awaited()

    async def test_admin_not_found(self, service, agent_repo):
        agent_repo.get_active.return_value = None
        agent_repo.admin_get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.get_profile(ADMIN, 1)


class TestCreateProfile:
    async def test_requires_admin(self, service, agent_repo):
        with pytest.raises(ForbiddenError):
            await service.create_profile(USER, "n", "d")

        agent_repo.create.assert_not_awaited()

    @pytest.mark.parametrize("name", ["", "  ", None])
    async def test_rejects_empty_name(self, service, name):
        with pytest.raises(ValueError, match="Profile name must not be empty"):
            await service.create_profile(ADMIN, name, "d")

    async def test_rejects_duplicate_name(self, service, agent_repo):
        agent_repo.admin_get_by_name.return_value = obj(5)

        with pytest.raises(ConflictError, match="Profile 'n' already exists"):
            await service.create_profile(ADMIN, " n ", "d")

        agent_repo.admin_get_by_name.assert_awaited_once_with("n")

    async def test_rejects_second_neutral_profile(self, service, agent_repo):
        agent_repo.get_neutral.return_value = obj(5)

        with pytest.raises(ConflictError, match="neutral profile already exists"):
            await service.create_profile(ADMIN, "n", "d", is_neutral=True)

    async def test_allows_first_neutral_profile(self, service, agent_repo):
        profile = obj(1)
        agent_repo.create.return_value = profile
        agent_repo.admin_get_by_id.return_value = profile

        await service.create_profile(ADMIN, "n", "d", is_neutral=True)

        agent_repo.create.assert_awaited_once_with(agent_name="n", description="d", is_neutral=True)

    async def test_creates_profile_with_skills_and_tools(
        self, service, agent_repo, skill_repo, tool_repo
    ):
        profile = obj(1)
        s1, s2, t = obj(1), obj(2), obj(10)
        skill_repo.get_global_active_many.return_value = [s1, s2]
        tool_repo.get_global_active_many.return_value = [t]
        agent_repo.create.return_value = profile
        agent_repo.admin_get_by_id.return_value = profile

        result = await service.create_profile(ADMIN, "n", "d", skill_ids=[1, 2, 2], tool_ids=[10])

        assert result is profile
        skill_repo.get_global_active_many.assert_awaited_once_with([1, 2])
        assert agent_repo.add_skill.await_count == 2
        agent_repo.add_tool.assert_awaited_once_with(profile, t)
        agent_repo.create.assert_awaited_once_with(agent_name="n", description="d", is_neutral=False)

    async def test_no_lookups_for_empty_lists(self, service, agent_repo, skill_repo, tool_repo):
        agent_repo.admin_get_by_id.return_value = obj(1)

        await service.create_profile(ADMIN, "n", "d")

        skill_repo.get_global_active_many.assert_not_awaited()
        tool_repo.get_global_active_many.assert_not_awaited()

    async def test_unavailable_skill_prevents_creation(self, service, agent_repo, skill_repo):
        skill_repo.get_global_active_many.return_value = []

        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_profile(ADMIN, "n", "d", skill_ids=[1])

        agent_repo.create.assert_not_awaited()

    async def test_unavailable_tool_prevents_creation(self, service, agent_repo, tool_repo):
        tool_repo.get_global_active_many.return_value = []

        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_profile(ADMIN, "n", "d", tool_ids=[1])

        agent_repo.create.assert_not_awaited()


class TestUpdateProfile:
    @pytest.fixture
    def profile(self, agent_repo):
        p = SimpleNamespace(
            id=1, description="old", skills=[obj(1), obj(2)], tools=[obj(10), obj(11)]
        )
        agent_repo.admin_get_by_id.return_value = p
        return p

    async def test_requires_admin(self, service, profile):
        with pytest.raises(ForbiddenError):
            await service.update_profile(USER, 1, description="x")

    async def test_not_found(self, service, agent_repo):
        agent_repo.admin_get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.update_profile(ADMIN, 1, description="x")

    async def test_updates_description_only_if_changed(self, service, agent_repo, profile):
        await service.update_profile(ADMIN, 1, description="old")
        agent_repo.update.assert_not_awaited()

        await service.update_profile(ADMIN, 1, description="new")
        agent_repo.update.assert_awaited_once_with(profile, description="new")

    async def test_none_leaves_skills_and_tools_untouched(self, service, agent_repo, profile):
        await service.update_profile(ADMIN, 1)

        agent_repo.add_skill.assert_not_awaited()
        agent_repo.remove_skill.assert_not_awaited()
        agent_repo.add_tool.assert_not_awaited()
        agent_repo.remove_tool.assert_not_awaited()

    async def test_syncs_skills_by_diff(self, service, agent_repo, skill_repo, profile):
        s2, s3 = obj(2), obj(3)
        skill_repo.get_global_active_many.return_value = [s2, s3]

        await service.update_profile(ADMIN, 1, skill_ids=[2, 3])

        agent_repo.add_skill.assert_awaited_once_with(profile, s3)
        agent_repo.remove_skill.assert_awaited_once_with(profile, profile.skills[0])

    async def test_empty_list_removes_all_tools(self, service, agent_repo, profile):
        await service.update_profile(ADMIN, 1, tool_ids=[])

        assert agent_repo.remove_tool.await_count == 2
        agent_repo.add_tool.assert_not_awaited()

    async def test_syncs_tools_by_diff(self, service, agent_repo, tool_repo, profile):
        t11, t12 = obj(11), obj(12)
        tool_repo.get_global_active_many.return_value = [t11, t12]

        await service.update_profile(ADMIN, 1, tool_ids=[11, 12])

        agent_repo.add_tool.assert_awaited_once_with(profile, t12)
        agent_repo.remove_tool.assert_awaited_once_with(profile, profile.tools[0])

    async def test_unavailable_skill_changes_nothing(self, service, agent_repo, skill_repo, profile):
        skill_repo.get_global_active_many.return_value = []

        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.update_profile(ADMIN, 1, description="new", skill_ids=[99])

        agent_repo.update.assert_not_awaited()


class TestArchiveRestore:
    async def test_archive_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.archive_profile(USER, 1)

    async def test_archives_profile(self, service, agent_repo):
        profile = SimpleNamespace(id=1, is_neutral=False)
        agent_repo.admin_get_by_id.return_value = profile

        result = await service.archive_profile(ADMIN, 1)

        agent_repo.archive.assert_awaited_once_with(profile)
        assert result is profile

    async def test_neutral_profile_cannot_be_archived(self, service, agent_repo):
        agent_repo.admin_get_by_id.return_value = SimpleNamespace(id=1, is_neutral=True)

        with pytest.raises(ConflictError, match="neutral profile cannot be archived"):
            await service.archive_profile(ADMIN, 1)

        agent_repo.archive.assert_not_awaited()

    async def test_archive_not_found(self, service, agent_repo):
        agent_repo.admin_get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.archive_profile(ADMIN, 1)

    async def test_restore_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.restore_profile(USER, 1)

    async def test_restores_profile(self, service, agent_repo):
        profile = SimpleNamespace(id=1, archived_at=datetime.now(timezone.utc))
        agent_repo.admin_get_by_id.return_value = profile

        await service.restore_profile(ADMIN, 1)

        agent_repo.restore.assert_awaited_once_with(profile)