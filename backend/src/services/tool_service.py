from src.repositories.tool_repo import ToolDefinitionRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.db.models.tools_definition import ToolDefinition


class ToolService:

    def __init__(
        self,
        tool_repo: ToolDefinitionRepository,
        domain_repo: KnowledgeDomainRepository,
    ):
        self.tool_repo = tool_repo
        self.domain_repo = domain_repo

    async def create_tool(
        self,
        tool_name: str,
        description: str,
        domain_ids: list[int],
    ) -> ToolDefinition:
        existing = await self.tool_repo.get_by_name(tool_name)
        if existing:
            raise ValueError(f"Tool '{tool_name}' already exists")

        tool = await self.tool_repo.create(
            tool_name=tool_name,
            description=description,
        )

        for domain_id in domain_ids:
            domain = await self.domain_repo.get_by_id(domain_id)
            if not domain:
                raise ValueError(f"Domain {domain_id} not found")
            await self.tool_repo.add_domain(tool, domain)

        return tool

    async def get_tools_by_domain(self, domain_id: int) -> list[ToolDefinition]:
        return await self.tool_repo.list_by_domain(domain_id)

    async def get_tool(self, tool_id: int) -> ToolDefinition:
        tool = await self.tool_repo.get_by_id(tool_id)
        if not tool:
            raise ValueError(f"Tool {tool_id} not found")
        return tool

    async def get_all_tools(self, limit: int = 100, offset: int = 0) -> list[ToolDefinition]:
        return list(await self.tool_repo.get_all(limit=limit, offset=offset))