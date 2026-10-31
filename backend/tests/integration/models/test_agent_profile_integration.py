import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from src.db.models.agent_profiles import AgentProfile
from src.db.models.config_bundles import ConfigBundle
from src.db.models.token_usage_events import TokenUsageEvent
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition

pytestmark = pytest.mark.integration


class TestAgentProfileDelete:

    async def test_deleting_agent_profile_sets_null_on_token_usage_events(
        self, db_session, sample_agent_profile, sample_user
    ):
        event = TokenUsageEvent(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            tokens_used=500,
        )
        db_session.add(event)
        await db_session.commit()
        event_id = event.id

        agent_to_delete = await db_session.get(AgentProfile, sample_agent_profile.id)
        await db_session.delete(agent_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(TokenUsageEvent)
            .where(TokenUsageEvent.id == event_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one().agent_id is None

    async def test_deleting_agent_profile_removes_skill_and_tool_associations_only(
        self, db_session, agent_profile_with_skill_and_tool, sample_skill, sample_tool
    ):
        agent_id = agent_profile_with_skill_and_tool.id

        agent_to_delete = await db_session.get(AgentProfile, agent_id)
        await db_session.delete(agent_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(Skill)
            .where(Skill.id == sample_skill.id)
            .options(selectinload(Skill.agent_profiles))
            .execution_options(populate_existing=True)
        )
        assert agent_id not in {ap.id for ap in result.scalar_one().agent_profiles}

        result = await db_session.execute(
            select(ToolDefinition)
            .where(ToolDefinition.id == sample_tool.id)
            .options(selectinload(ToolDefinition.agent_profiles))
            .execution_options(populate_existing=True)
        )
        assert agent_id not in {ap.id for ap in result.scalar_one().agent_profiles}

    async def test_cannot_create_bundle_with_deleted_agent_id(
        self, db_session, sample_user, sample_agent_profile
    ):
        agent_id = sample_agent_profile.id

        agent_to_delete = await db_session.get(AgentProfile, agent_id)
        await db_session.delete(agent_to_delete)
        await db_session.commit()

        db_session.add(
            ConfigBundle(
                user_id=sample_user.id,
                agent_id=agent_id,
                name="dangling-agent-ref",
                description="Should fail, agent was deleted",
            )
        )

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()