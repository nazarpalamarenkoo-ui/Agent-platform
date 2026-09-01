import pytest

from src.repositories.tool_repo import ToolDefinitionRepository

pytestmark = pytest.mark.db


@pytest.fixture
def tool_repo(db_session):
    return ToolDefinitionRepository(db_session)


class TestToolDefinitionRepository:

    async def test_get_by_name_found(self, tool_repo, sample_tool):
        found = await tool_repo.get_by_name(sample_tool.tool_name)

        assert found is not None
        assert found.id == sample_tool.id

    async def test_get_by_name_not_found(self, tool_repo):
        found = await tool_repo.get_by_name("nonexistent-tool")

        assert found is None

    async def test_record_selection_increments_freq(
        self, tool_repo, sample_tool, sample_user
    ):
        initial_freq = sample_tool.tool_selected_freq

        await tool_repo.record_selection(sample_tool.id, sample_user.id)

        assert sample_tool.tool_selected_freq == initial_freq + 1

    async def test_record_selection_returns_tool(
        self, tool_repo, sample_tool, sample_user
    ):
        result = await tool_repo.record_selection(sample_tool.id, sample_user.id)

        assert result is not None
        assert result.id == sample_tool.id

    async def test_record_selection_with_config_bundle(
        self, tool_repo, sample_tool, sample_user, sample_config_bundle
    ):
        result = await tool_repo.record_selection(
            sample_tool.id, sample_user.id, config_bundle_id=sample_config_bundle.id
        )

        assert result is not None

    async def test_record_selection_unknown_tool_raises(
        self, tool_repo, sample_user
    ):
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await tool_repo.record_selection(999999, sample_user.id)

    async def test_list_by_domain_returns_tools(
        self, tool_repo, domain_scoped_tool, another_knowledge_domain
    ):
        results = await tool_repo.list_by_domain(another_knowledge_domain.id)

        ids = {t.id for t in results}
        assert domain_scoped_tool.id in ids

    async def test_list_by_domain_empty_for_unknown(self, tool_repo):
        results = await tool_repo.list_by_domain(999999)

        assert results == []

    async def test_list_by_domain_excludes_other_domains(
        self, tool_repo, domain_scoped_tool, sample_knowledge_domain
    ):
        results = await tool_repo.list_by_domain(sample_knowledge_domain.id)

        ids = {t.id for t in results}
        assert domain_scoped_tool.id not in ids