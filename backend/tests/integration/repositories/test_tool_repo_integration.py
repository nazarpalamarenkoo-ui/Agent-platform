import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.repositories.tool_repo import ToolDefinitionRepository
from src.db.models.tool_usage_events import ToolUsageEvent

pytestmark = pytest.mark.integration


@pytest.fixture
def tool_repo(db_session):
    return ToolDefinitionRepository(db_session)


class TestToolUniqueConstraints:

    async def test_cannot_create_two_tools_with_same_name(
        self, tool_repo, db_session
    ):
        await tool_repo.create(
            tool_name="duplicate-tool",
            description="First",
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await tool_repo.create(
                tool_name="duplicate-tool",
                description="Second",
            )
            await db_session.commit()

        await db_session.rollback()


class TestToolRecordSelectionSideEffects:

    async def test_record_selection_persists_usage_event(
        self, tool_repo, db_session, sample_tool, sample_user
    ):
        await tool_repo.record_selection(sample_tool.id, sample_user.id)
        await db_session.commit()

        result = await db_session.execute(
            select(ToolUsageEvent)
            .where(ToolUsageEvent.tool_id == sample_tool.id)
            .where(ToolUsageEvent.user_id == sample_user.id)
        )
        events = result.scalars().all()

        assert len(events) >= 1

    async def test_record_selection_freq_increment_is_persisted(
        self, tool_repo, db_session, sample_tool, sample_user
    ):
        initial_freq = sample_tool.tool_selected_freq

        await tool_repo.record_selection(sample_tool.id, sample_user.id)
        await db_session.commit()

        tool_id = sample_tool.id
        db_session.expire(sample_tool)
        reloaded = await tool_repo.get_by_id(tool_id)

        assert reloaded.tool_selected_freq == initial_freq + 1

    async def test_multiple_selections_accumulate_freq(
        self, tool_repo, db_session, sample_tool, sample_user
    ):
        initial_freq = sample_tool.tool_selected_freq

        for _ in range(3):
            await tool_repo.record_selection(sample_tool.id, sample_user.id)
        await db_session.commit()

        tool_id = sample_tool.id
        db_session.expire(sample_tool)
        reloaded = await tool_repo.get_by_id(tool_id)

        assert reloaded.tool_selected_freq == initial_freq + 3

    async def test_record_selection_with_config_bundle_persists_event(
        self, tool_repo, db_session, sample_tool, sample_user, sample_config_bundle
    ):
        await tool_repo.record_selection(
            sample_tool.id, sample_user.id, config_bundle_id=sample_config_bundle.id
        )
        await db_session.commit()

        result = await db_session.execute(
            select(ToolUsageEvent)
            .where(ToolUsageEvent.tool_id == sample_tool.id)
            .where(ToolUsageEvent.config_bundle_id == sample_config_bundle.id)
        )
        events = result.scalars().all()

        assert len(events) >= 1


class TestToolDeleteBehaviour:

    async def test_deleting_tool_cascades_usage_events(
        self, tool_repo, db_session, sample_tool, sample_user
    ):
        event = ToolUsageEvent(
            tool_id=sample_tool.id,
            user_id=sample_user.id,
        )
        db_session.add(event)
        await db_session.commit()
        event_id = event.id

        await tool_repo.delete(sample_tool)
        await db_session.commit()

        result = await db_session.execute(
            select(ToolUsageEvent)
            .where(ToolUsageEvent.id == event_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is None