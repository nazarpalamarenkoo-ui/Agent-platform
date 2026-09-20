import pytest

from src.services.tool_service import ToolService
from src.repositories.tool_repo import ToolDefinitionRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository


@pytest.fixture
def service(db_session):
    return ToolService(
        ToolDefinitionRepository(db_session),
        KnowledgeDomainRepository(db_session),
    )


class TestCreateTool:
    async def test_persists_tool_with_real_domain_links(
        self, service, sample_knowledge_domain
    ):
        tool = await service.create_tool(
            tool_name="web-search",
            description="Searches the web",
            domain_ids=[sample_knowledge_domain.id],
        )

        assert tool.id is not None

        reloaded = await service.get_tool(tool.id)
        assert reloaded.tool_name == "web-search"
        assert [d.id for d in reloaded.domains] == [sample_knowledge_domain.id]

    async def test_raises_when_tool_name_already_exists(
        self, service, sample_knowledge_domain
    ):
        await service.create_tool(
            tool_name="dup-tool",
            description="d",
            domain_ids=[sample_knowledge_domain.id],
        )

        with pytest.raises(ValueError, match="Tool 'dup-tool' already exists"):
            await service.create_tool(
                tool_name="dup-tool",
                description="d2",
                domain_ids=[sample_knowledge_domain.id],
            )

    async def test_partially_links_domains_when_a_later_domain_id_is_invalid(
        self, service, sample_knowledge_domain
    ):
        # documents actual behaviour: the tool is created before domains are
        # linked, so a failure partway through the loop leaves it persisted
        # with only the domains that were already attached.
        with pytest.raises(ValueError, match="Domain 999999 not found"):
            await service.create_tool(
                tool_name="partial-tool",
                description="d",
                domain_ids=[sample_knowledge_domain.id, 999_999],
            )

        linked = await service.get_tools_by_domain(sample_knowledge_domain.id)
        assert "partial-tool" in [t.tool_name for t in linked]

    async def test_raises_when_first_domain_id_is_invalid(self, service):
        with pytest.raises(ValueError, match="Domain 999999 not found"):
            await service.create_tool(
                tool_name="orphan-tool", description="d", domain_ids=[999_999]
            )


class TestGetToolsByDomain:
    async def test_returns_only_tools_linked_to_that_domain(
        self, service, sample_knowledge_domain, another_knowledge_domain
    ):
        await service.create_tool(
            tool_name="tool-a", description="d", domain_ids=[sample_knowledge_domain.id]
        )
        await service.create_tool(
            tool_name="tool-b", description="d", domain_ids=[another_knowledge_domain.id]
        )

        result = await service.get_tools_by_domain(sample_knowledge_domain.id)
        names = {t.tool_name for t in result}

        assert "tool-a" in names
        assert "tool-b" not in names


class TestGetTool:
    async def test_returns_persisted_tool(self, service, sample_knowledge_domain):
        created = await service.create_tool(
            tool_name="lookup-tool", description="d", domain_ids=[sample_knowledge_domain.id]
        )

        result = await service.get_tool(created.id)
        assert result.id == created.id

    async def test_raises_for_unknown_id(self, service):
        with pytest.raises(ValueError, match="Tool 999999 not found"):
            await service.get_tool(999_999)


class TestGetAllTools:
    async def test_returns_all_created_tools(self, service, sample_knowledge_domain):
        t1 = await service.create_tool(
            tool_name="all-tool-1", description="d", domain_ids=[sample_knowledge_domain.id]
        )
        t2 = await service.create_tool(
            tool_name="all-tool-2", description="d", domain_ids=[sample_knowledge_domain.id]
        )

        result = await service.get_all_tools()
        ids = {t.id for t in result}

        assert t1.id in ids
        assert t2.id in ids

    async def test_respects_limit_and_offset(self, service, sample_knowledge_domain):
        await service.create_tool(
            tool_name="page-tool-1", description="d", domain_ids=[sample_knowledge_domain.id]
        )
        await service.create_tool(
            tool_name="page-tool-2", description="d", domain_ids=[sample_knowledge_domain.id]
        )

        first_page = await service.get_all_tools(limit=1, offset=0)
        second_page = await service.get_all_tools(limit=1, offset=1)

        assert len(first_page) == 1
        assert len(second_page) == 1
        assert first_page[0].id != second_page[0].id