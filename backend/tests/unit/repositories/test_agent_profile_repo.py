import pytest

from src.repositories.agent_profile_repo import AgentProfileRepository

pytestmark = pytest.mark.db


@pytest.fixture
def agent_repo(db_session):
    return AgentProfileRepository(db_session)


class TestAgentProfileRepository:

    async def test_get_by_id_loads_relations(self, agent_repo, agent_profile_with_skill_and_tool):
        found = await agent_repo.get_by_id(agent_profile_with_skill_and_tool.id)

        assert found is not None
        assert len(found.skills) == 1
        assert len(found.tools) == 1

    async def test_get_by_id_returns_none_when_missing(self, agent_repo):
        found = await agent_repo.get_by_id(999999)

        assert found is None

    async def test_get_by_name_found(self, agent_repo, sample_agent_profile):
        found = await agent_repo.get_by_name(sample_agent_profile.agent_name)

        assert found is not None
        assert found.id == sample_agent_profile.id

    async def test_get_by_name_not_found(self, agent_repo):
        found = await agent_repo.get_by_name("does-not-exist")

        assert found is None

    async def test_add_skill_appends_once(self, agent_repo, sample_agent_profile, sample_skill):
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await agent_repo.add_skill(sample_agent_profile, sample_skill)

        assert len(sample_agent_profile.skills) == 1

    async def test_remove_skill_removes_existing(self, agent_repo, sample_agent_profile, sample_skill):
        await agent_repo.add_skill(sample_agent_profile, sample_skill)

        await agent_repo.remove_skill(sample_agent_profile, sample_skill)

        assert sample_skill not in sample_agent_profile.skills

    async def test_remove_skill_noop_when_absent(self, agent_repo, sample_agent_profile, sample_skill):
        result = await agent_repo.remove_skill(sample_agent_profile, sample_skill)

        assert result is sample_agent_profile
        assert sample_skill not in sample_agent_profile.skills

    async def test_add_tool_appends_once(self, agent_repo, sample_agent_profile, sample_tool):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await agent_repo.add_tool(sample_agent_profile, sample_tool)

        assert len(sample_agent_profile.tools) == 1

    async def test_remove_tool_removes_existing(self, agent_repo, sample_agent_profile, sample_tool):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)

        await agent_repo.remove_tool(sample_agent_profile, sample_tool)

        assert sample_tool not in sample_agent_profile.tools

    async def test_remove_tool_noop_when_absent(self, agent_repo, sample_agent_profile, sample_tool):
        result = await agent_repo.remove_tool(sample_agent_profile, sample_tool)

        assert result is sample_agent_profile
        assert sample_tool not in sample_agent_profile.tools