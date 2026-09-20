from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.tool_service import ToolService


@pytest.fixture
def tool_repo():
    return AsyncMock()


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def service(tool_repo, domain_repo):
    return ToolService(tool_repo, domain_repo)


class TestCreateTool:
    async def test_creates_tool_with_domains(
        self, service, tool_repo, domain_repo
    ):
        tool_repo.get_by_name.return_value = None
        tool = MagicMock()
        tool_repo.create.return_value = tool
        domain_repo.get_by_id.return_value = MagicMock()

        result = await service.create_tool(
            tool_name="web_search", description="desc", domain_ids=[1, 2]
        )

        assert result is tool
        tool_repo.create.assert_awaited_once_with(
            tool_name="web_search", description="desc"
        )
        assert domain_repo.get_by_id.await_count == 2
        assert tool_repo.add_domain.await_count == 2

    async def test_creates_tool_with_no_domains(
        self, service, tool_repo, domain_repo
    ):
        tool_repo.get_by_name.return_value = None
        tool = MagicMock()
        tool_repo.create.return_value = tool

        result = await service.create_tool(
            tool_name="web_search", description="desc", domain_ids=[]
        )

        assert result is tool
        domain_repo.get_by_id.assert_not_awaited()

    async def test_raises_when_tool_name_taken(self, service, tool_repo):
        tool_repo.get_by_name.return_value = MagicMock()

        with pytest.raises(ValueError, match="Tool 'web_search' already exists"):
            await service.create_tool(
                tool_name="web_search", description="desc", domain_ids=[]
            )

        tool_repo.create.assert_not_awaited()

    async def test_raises_when_domain_not_found(
        self, service, tool_repo, domain_repo
    ):
        tool_repo.get_by_name.return_value = None
        tool_repo.create.return_value = MagicMock()
        domain_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Domain 1 not found"):
            await service.create_tool(
                tool_name="web_search", description="desc", domain_ids=[1]
            )


class TestGetToolsByDomain:
    async def test_delegates_to_repo(self, service, tool_repo):
        tools = [MagicMock()]
        tool_repo.list_by_domain.return_value = tools

        result = await service.get_tools_by_domain(domain_id=1)

        assert result is tools
        tool_repo.list_by_domain.assert_awaited_once_with(1)


class TestGetTool:
    async def test_returns_tool_when_found(self, service, tool_repo):
        tool = MagicMock()
        tool_repo.get_by_id.return_value = tool

        result = await service.get_tool(1)

        assert result is tool

    async def test_raises_when_not_found(self, service, tool_repo):
        tool_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Tool 1 not found"):
            await service.get_tool(1)


class TestGetAllTools:
    async def test_returns_list_with_default_pagination(
        self, service, tool_repo
    ):
        tool_repo.get_all.return_value = (MagicMock(),)

        result = await service.get_all_tools()

        assert isinstance(result, list)
        assert len(result) == 1
        tool_repo.get_all.assert_awaited_once_with(limit=100, offset=0)

    async def test_returns_list_with_custom_pagination(
        self, service, tool_repo
    ):
        tool_repo.get_all.return_value = []

        await service.get_all_tools(limit=20, offset=40)

        tool_repo.get_all.assert_awaited_once_with(limit=20, offset=40)