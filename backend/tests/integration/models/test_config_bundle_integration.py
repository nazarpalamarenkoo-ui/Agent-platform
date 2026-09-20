import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.models.config_bundles import ConfigBundle
from src.db.models.skill_usage_events import SkillUsageEvent
from src.db.models.tool_usage_events import ToolUsageEvent

pytestmark = pytest.mark.integration

class TestConfigBundleCompositeUniqueConstraint:

    async def test_same_user_cannot_create_two_bundles_with_same_name(
        self, db_session, sample_user, sample_agent_profile
    ):
        bundle = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="duplicate-name",
            description="Original bundle",
        )
        db_session.add(bundle)
        await db_session.commit()

        duplicate = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="duplicate-name",
            description="Duplicate bundle, same user",
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_different_user_can_create_bundle_with_same_name(
        self, db_session, sample_user, another_user, sample_agent_profile
    ):
        bundle = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="shared-name",
            description="Bundle owned by sample_user",
        )
        db_session.add(bundle)
        await db_session.commit()

        other_bundle = ConfigBundle(
            user_id=another_user.id,
            agent_id=sample_agent_profile.id,
            name="shared-name",
            description="Bundle owned by another_user",
        )
        db_session.add(other_bundle)
        
        await db_session.commit()
        await db_session.refresh(other_bundle)

        assert other_bundle.id is not None
        assert other_bundle.name == "shared-name"
        assert other_bundle.user_id == another_user.id

    async def test_same_user_can_reuse_name_after_original_bundle_deleted(
        self, db_session, sample_user, sample_agent_profile
    ):
        bundle = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="reusable-name",
            description="Will be deleted",
        )
        db_session.add(bundle)
        await db_session.commit()

        await db_session.delete(bundle)
        await db_session.commit()

        recreated = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="reusable-name",
            description="Recreated with the same name",
        )
        db_session.add(recreated)
        await db_session.commit()
        await db_session.refresh(recreated)

        assert recreated.id is not None


class TestConfigBundleForeignKeyIntegrity:

    async def test_cannot_create_config_bundle_with_nonexistent_user_id(
        self, db_session, sample_agent_profile
    ):
        nonexistent_user_id = 999_999

        bundle = ConfigBundle(
            user_id=nonexistent_user_id,
            agent_id=sample_agent_profile.id,
            name="orphan-bundle",
            description="Bundle referencing a user that does not exist",
        )
        db_session.add(bundle)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_cannot_create_config_bundle_with_nonexistent_agent_id(
        self, db_session, sample_user
    ):
        nonexistent_agent_id = 999_999

        bundle = ConfigBundle(
            user_id=sample_user.id,
            agent_id=nonexistent_agent_id,
            name="orphan-bundle-agent",
            description="Bundle referencing an agent profile that does not exist",
        )
        db_session.add(bundle)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()


class TestConfigBundleDeleteBehaviour:

    async def test_deleting_config_bundle_sets_null_on_usage_events(
        self,
        db_session,
        sample_config_bundle,
        sample_skill,
        sample_tool,
        sample_user,
    ):
        skill_event = SkillUsageEvent(
            skill_id=sample_skill.id,
            user_id=sample_user.id,
            config_bundle_id=sample_config_bundle.id,
        )
        tool_event = ToolUsageEvent(
            tool_id=sample_tool.id,
            user_id=sample_user.id,
            config_bundle_id=sample_config_bundle.id,
        )
        db_session.add_all([skill_event, tool_event])
        await db_session.commit()

        skill_event_id = skill_event.id
        tool_event_id = tool_event.id

        bundle_to_delete = await db_session.get(ConfigBundle, sample_config_bundle.id)
        await db_session.delete(bundle_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(SkillUsageEvent)
            .where(SkillUsageEvent.id == skill_event_id)
            .execution_options(populate_existing=True)
        )
        reloaded_skill_event = result.scalar_one()
        assert reloaded_skill_event.config_bundle_id is None

        result = await db_session.execute(
            select(ToolUsageEvent)
            .where(ToolUsageEvent.id == tool_event_id)
            .execution_options(populate_existing=True)
        )
        reloaded_tool_event = result.scalar_one()
        assert reloaded_tool_event.config_bundle_id is None

    async def test_deleting_config_bundle_removes_skill_and_tool_associations(
        self, db_session, config_bundle_with_skill_and_tool, sample_skill, sample_tool
    ):
        bundle_id = config_bundle_with_skill_and_tool.id

        bundle_to_delete = await db_session.get(ConfigBundle, bundle_id)
        await db_session.delete(bundle_to_delete)
        await db_session.commit()

        from src.db.models.skills import Skill
        from src.db.models.tools_definition import ToolDefinition

        result = await db_session.execute(
            select(Skill)
            .where(Skill.id == sample_skill.id)
            .execution_options(populate_existing=True)
        )
        reloaded_skill = result.scalar_one()
        assert bundle_id not in {cb.id for cb in reloaded_skill.config_bundles}

        result = await db_session.execute(
            select(ToolDefinition)
            .where(ToolDefinition.id == sample_tool.id)
            .execution_options(populate_existing=True)
        )
        reloaded_tool = result.scalar_one()
        assert bundle_id not in {cb.id for cb in reloaded_tool.config_bundles}