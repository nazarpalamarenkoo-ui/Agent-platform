import pytest

from src.services.agent_profile_service import AgentProfileService
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository


@pytest.fixture
def service(db_session):
    return AgentProfileService(
        AgentProfileRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
    )


class TestCreateProfile:
    async def test_persists_profile_with_real_skill_and_tool_links(
        self, service, db_session, sample_skill, sample_tool
    ):
        profile = await service.create_profile(
            name="research-agent",
            description="Looks things up",
            skill_ids=[sample_skill.id],
            tool_ids=[sample_tool.id],
        )

        assert profile.id is not None

        reloaded = await service.get_profile(profile.id)
        assert reloaded.agent_name == "research-agent"
        assert [s.id for s in reloaded.skills] == [sample_skill.id]
        assert [t.id for t in reloaded.tools] == [sample_tool.id]

    async def test_raises_and_does_not_link_tools_when_skill_id_invalid(
        self, service, sample_tool
    ):
        with pytest.raises(ValueError, match="Skill 999999 not found"):
            await service.create_profile(
                name="broken-agent",
                description="d",
                skill_ids=[999_999],
                tool_ids=[sample_tool.id],
            )

    async def test_raises_when_tool_id_invalid(self, service, sample_skill):
        with pytest.raises(ValueError, match="Tool 999999 not found"):
            await service.create_profile(
                name="broken-agent",
                description="d",
                skill_ids=[sample_skill.id],
                tool_ids=[999_999],
            )


class TestGetProfile:
    async def test_returns_persisted_profile(self, service, sample_agent_profile):
        result = await service.get_profile(sample_agent_profile.id)

        assert result.id == sample_agent_profile.id
        assert result.agent_name == "test-agent"

    async def test_raises_for_unknown_id(self, service):
        with pytest.raises(ValueError, match="Agent profile 999999 not found"):
            await service.get_profile(999_999)


class TestGetAllProfiles:
    async def test_returns_all_created_profiles(
        self, service, sample_agent_profile, another_agent_profile
    ):
        profiles = await service.get_all_profiles()

        ids = {p.id for p in profiles}
        assert sample_agent_profile.id in ids
        assert another_agent_profile.id in ids

    async def test_respects_limit_and_offset(
        self, service, sample_agent_profile, another_agent_profile
    ):
        first_page = await service.get_all_profiles(limit=1, offset=0)
        second_page = await service.get_all_profiles(limit=1, offset=1)

        assert len(first_page) == 1
        assert len(second_page) == 1
        assert first_page[0].id != second_page[0].id