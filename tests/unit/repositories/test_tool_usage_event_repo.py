import pytest

from src.repositories.tool_usage_event_repo import ToolUsageEventRepository

pytestmark = pytest.mark.db


@pytest.fixture
def tool_event_repo(db_session):
    return ToolUsageEventRepository(db_session)


class TestToolUsageEventRepository:

    async def test_get_for_tool_returns_events(
        self, tool_event_repo, sample_tool_usage_event, sample_tool
    ):
        results = await tool_event_repo.get_for_tool(sample_tool.id)

        ids = {e.id for e in results}
        assert sample_tool_usage_event.id in ids

    async def test_get_for_tool_empty_when_no_events(self, tool_event_repo):
        results = await tool_event_repo.get_for_tool(999999)

        assert results == []

    async def test_get_for_tool_respects_limit(
        self, tool_event_repo, sample_tool, sample_user, sample_config_bundle
    ):
        from src.db.models.tool_usage_events import ToolUsageEvent

        for _ in range(5):
            tool_event_repo.session.add(
                ToolUsageEvent(
                    tool_id=sample_tool.id,
                    user_id=sample_user.id,
                    config_bundle_id=sample_config_bundle.id,
                )
            )
        await tool_event_repo.session.flush()

        results = await tool_event_repo.get_for_tool(sample_tool.id, limit=3)

        assert len(results) <= 3

    async def test_get_for_config_bundle_returns_events(
        self, tool_event_repo, sample_tool_usage_event, sample_config_bundle
    ):
        results = await tool_event_repo.get_for_config_bundle(sample_config_bundle.id)

        ids = {e.id for e in results}
        assert sample_tool_usage_event.id in ids

    async def test_get_for_config_bundle_loads_tool_relation(
        self, tool_event_repo, sample_tool_usage_event, sample_config_bundle
    ):
        results = await tool_event_repo.get_for_config_bundle(sample_config_bundle.id)

        assert len(results) > 0
        assert results[0].tool is not None

    async def test_get_for_config_bundle_empty_for_unknown(self, tool_event_repo):
        results = await tool_event_repo.get_for_config_bundle(999999)

        assert results == []