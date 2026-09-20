from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.agent_profile_service import AgentProfileService


@pytest.fixture
def agent_repo():
    return AsyncMock()


@pytest.fixture
def skill_repo():
    return AsyncMock()


@pytest.fixture
def tool_repo():
    return AsyncMock()


@pytest.fixture
def service(agent_repo, skill_repo, tool_repo):
    return AgentProfileService(agent_repo, skill_repo, tool_repo)


class TestCreateProfile:
    async def test_creates_profile_with_skills_and_tools(
        self, service, agent_repo, skill_repo, tool_repo
    ):
        profile = MagicMock()
        agent_repo.create.return_value = profile
        skill_repo.get_by_id.return_value = MagicMock()
        tool_repo.get_by_id.return_value = MagicMock()

        result = await service.create_profile(
            name="agent-1",
            description="desc",
            skill_ids=[1, 2],
            tool_ids=[10],
        )

        assert result is profile
        agent_repo.create.assert_awaited_once_with(
            agent_name="agent-1", description="desc"
        )
        assert skill_repo.get_by_id.await_count == 2
        assert agent_repo.add_skill.await_count == 2
        tool_repo.get_by_id.assert_awaited_once_with(10)
        agent_repo.add_tool.assert_awaited_once()

    async def test_creates_profile_with_no_skills_or_tools(
        self, service, agent_repo, skill_repo, tool_repo
    ):
        profile = MagicMock()
        agent_repo.create.return_value = profile

        result = await service.create_profile(
            name="agent-1", description="desc", skill_ids=[], tool_ids=[]
        )

        assert result is profile
        skill_repo.get_by_id.assert_not_awaited()
        tool_repo.get_by_id.assert_not_awaited()
        agent_repo.add_skill.assert_not_awaited()
        agent_repo.add_tool.assert_not_awaited()

    async def test_raises_when_skill_not_found(
        self, service, agent_repo, skill_repo
    ):
        agent_repo.create.return_value = MagicMock()
        skill_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Skill 1 not found"):
            await service.create_profile(
                name="agent-1", description="desc", skill_ids=[1], tool_ids=[]
            )

    async def test_raises_when_tool_not_found(
        self, service, agent_repo, tool_repo
    ):
        agent_repo.create.return_value = MagicMock()
        tool_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Tool 5 not found"):
            await service.create_profile(
                name="agent-1", description="desc", skill_ids=[], tool_ids=[5]
            )

    async def test_does_not_add_tools_if_skill_lookup_fails(
        self, service, agent_repo, skill_repo, tool_repo
    ):
        agent_repo.create.return_value = MagicMock()
        skill_repo.get_by_id.return_value = None

        with pytest.raises(ValueError):
            await service.create_profile(
                name="agent-1",
                description="desc",
                skill_ids=[1],
                tool_ids=[10],
            )

        tool_repo.get_by_id.assert_not_awaited()


class TestGetProfile:
    async def test_returns_profile_when_found(self, service, agent_repo):
        profile = MagicMock()
        agent_repo.get_by_id.return_value = profile

        result = await service.get_profile(42)

        assert result is profile
        agent_repo.get_by_id.assert_awaited_once_with(42)

    async def test_raises_when_not_found(self, service, agent_repo):
        agent_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Agent profile 42 not found"):
            await service.get_profile(42)


class TestGetAllProfiles:
    async def test_delegates_to_repo_with_defaults(self, service, agent_repo):
        profiles = [MagicMock(), MagicMock()]
        agent_repo.get_all.return_value = profiles

        result = await service.get_all_profiles()

        assert result is profiles
        agent_repo.get_all.assert_awaited_once_with(limit=100, offset=0)

    async def test_delegates_to_repo_with_custom_pagination(
        self, service, agent_repo
    ):
        agent_repo.get_all.return_value = []

        await service.get_all_profiles(limit=10, offset=20)

        agent_repo.get_all.assert_awaited_once_with(limit=10, offset=20)