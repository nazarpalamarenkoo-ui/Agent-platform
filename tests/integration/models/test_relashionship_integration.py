import pytest
from sqlalchemy import select

from src.db.models.config_bundles import ConfigBundle
from src.db.models.agent_profiles import AgentProfile
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition


pytestmark = pytest.mark.integration


class TestConfigBundleSkillRelationship:

    async def test_config_bundle_skill_relationship_persists(
        self, db_session, sample_config_bundle, sample_skill, another_skill
    ):
        sample_config_bundle.skills.extend([sample_skill, another_skill])
        db_session.add(sample_config_bundle)
        await db_session.commit()

        result = await db_session.execute(
            select(ConfigBundle).where(ConfigBundle.id == sample_config_bundle.id)
        )
        reloaded_bundle = result.scalar_one()
        assert {s.id for s in reloaded_bundle.skills} == {
            sample_skill.id,
            another_skill.id,
        }

        result = await db_session.execute(
            select(Skill).where(Skill.id == sample_skill.id)
        )
        reloaded_skill = result.scalar_one()
        assert sample_config_bundle.id in {
            cb.id for cb in reloaded_skill.config_bundles
        }

    async def test_removing_skill_from_bundle_does_not_delete_skill(
        self, db_session, config_bundle_with_skill_and_tool, sample_skill
    ):
        bundle_id = config_bundle_with_skill_and_tool.id

        result = await db_session.execute(
            select(ConfigBundle).where(ConfigBundle.id == bundle_id)
        )
        bundle = result.scalar_one()
        bundle.skills.remove(sample_skill)
        db_session.add(bundle)
        await db_session.commit()

        result = await db_session.execute(
            select(ConfigBundle).where(ConfigBundle.id == bundle_id)
        )
        reloaded_bundle = result.scalar_one()
        assert sample_skill.id not in {s.id for s in reloaded_bundle.skills}
        result = await db_session.execute(
            select(Skill).where(Skill.id == sample_skill.id)
        )
        assert result.scalar_one_or_none() is not None


class TestConfigBundleToolRelationship:

    async def test_config_bundle_tool_relationship_persists(
        self, db_session, sample_config_bundle, sample_tool, another_tool
    ):
        sample_config_bundle.tools.extend([sample_tool, another_tool])
        db_session.add(sample_config_bundle)
        await db_session.commit()

        result = await db_session.execute(
            select(ConfigBundle).where(ConfigBundle.id == sample_config_bundle.id)
        )
        reloaded_bundle = result.scalar_one()
        assert {t.id for t in reloaded_bundle.tools} == {
            sample_tool.id,
            another_tool.id,
        }

        result = await db_session.execute(
            select(ToolDefinition).where(ToolDefinition.id == sample_tool.id)
        )
        reloaded_tool = result.scalar_one()
        assert sample_config_bundle.id in {
            cb.id for cb in reloaded_tool.config_bundles
        }

    async def test_removing_tool_from_bundle_does_not_delete_tool(
        self, db_session, config_bundle_with_skill_and_tool, sample_tool
    ):
        bundle_id = config_bundle_with_skill_and_tool.id

        result = await db_session.execute(
            select(ConfigBundle).where(ConfigBundle.id == bundle_id)
        )
        bundle = result.scalar_one()
        bundle.tools.remove(sample_tool)
        db_session.add(bundle)
        await db_session.commit()

        result = await db_session.execute(
            select(ConfigBundle).where(ConfigBundle.id == bundle_id)
        )
        reloaded_bundle = result.scalar_one()
        assert sample_tool.id not in {t.id for t in reloaded_bundle.tools}

        result = await db_session.execute(
            select(ToolDefinition).where(ToolDefinition.id == sample_tool.id)
        )
        assert result.scalar_one_or_none() is not None


class TestAgentProfileSkillRelationship:

    async def test_agent_profile_skill_relationship_persists(
        self, db_session, sample_agent_profile, sample_skill, another_skill
    ):
        sample_agent_profile.skills.extend([sample_skill, another_skill])
        db_session.add(sample_agent_profile)
        await db_session.commit()

        result = await db_session.execute(
            select(AgentProfile).where(AgentProfile.id == sample_agent_profile.id)
        )
        reloaded_agent = result.scalar_one()
        assert {s.id for s in reloaded_agent.skills} == {
            sample_skill.id,
            another_skill.id,
        }

        result = await db_session.execute(
            select(Skill).where(Skill.id == sample_skill.id)
        )
        reloaded_skill = result.scalar_one()
        assert sample_agent_profile.id in {
            ap.id for ap in reloaded_skill.agent_profiles
        }


class TestAgentProfileToolRelationship:

    async def test_agent_profile_tool_relationship_persists(
        self, db_session, sample_agent_profile, sample_tool, another_tool
    ):
        sample_agent_profile.tools.extend([sample_tool, another_tool])
        db_session.add(sample_agent_profile)
        await db_session.commit()

        result = await db_session.execute(
            select(AgentProfile).where(AgentProfile.id == sample_agent_profile.id)
        )
        reloaded_agent = result.scalar_one()
        assert {t.id for t in reloaded_agent.tools} == {
            sample_tool.id,
            another_tool.id,
        }

        result = await db_session.execute(
            select(ToolDefinition).where(ToolDefinition.id == sample_tool.id)
        )
        reloaded_tool = result.scalar_one()
        assert sample_agent_profile.id in {
            ap.id for ap in reloaded_tool.agent_profiles
        }


class TestSharedSkillsAndToolsAcrossMultipleParents:

    async def test_same_skill_can_belong_to_bundle_and_agent_profile(
        self,
        db_session,
        sample_config_bundle,
        sample_agent_profile,
        sample_skill,
    ):
        sample_config_bundle.skills.append(sample_skill)
        sample_agent_profile.skills.append(sample_skill)
        db_session.add_all([sample_config_bundle, sample_agent_profile])
        await db_session.commit()

        result = await db_session.execute(
            select(Skill).where(Skill.id == sample_skill.id)
        )
        reloaded_skill = result.scalar_one()

        assert sample_config_bundle.id in {
            cb.id for cb in reloaded_skill.config_bundles
        }
        assert sample_agent_profile.id in {
            ap.id for ap in reloaded_skill.agent_profiles
        }

    async def test_same_tool_can_belong_to_bundle_and_agent_profile(
        self,
        db_session,
        sample_config_bundle,
        sample_agent_profile,
        sample_tool,
    ):
        sample_config_bundle.tools.append(sample_tool)
        sample_agent_profile.tools.append(sample_tool)
        db_session.add_all([sample_config_bundle, sample_agent_profile])
        await db_session.commit()

        result = await db_session.execute(
            select(ToolDefinition).where(ToolDefinition.id == sample_tool.id)
        )
        reloaded_tool = result.scalar_one()

        assert sample_config_bundle.id in {
            cb.id for cb in reloaded_tool.config_bundles
        }
        assert sample_agent_profile.id in {
            ap.id for ap in reloaded_tool.agent_profiles
        }