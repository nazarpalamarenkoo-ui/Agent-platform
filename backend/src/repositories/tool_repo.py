from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.base_repo import BaseRepository
from src.db.models.tools_definition import ToolDefinition
from src.db.models.tool_domain import ToolDomain
from src.db.models.tool_usage_events import ToolUsageEvent
from src.db.models.knowledge_domains import KnowledgeDomain


class ToolDefinitionRepository(BaseRepository[ToolDefinition]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, ToolDefinition)

    async def get_by_name(self, tool_name: str) -> Optional[ToolDefinition]:
        result = await self.session.execute(
            select(ToolDefinition).where(ToolDefinition.tool_name == tool_name)
        )
        return result.scalar_one_or_none()

    async def record_selection(
        self,
        tool_id: int,
        user_id: int,
        config_bundle_id: int | None = None,
    ) -> Optional[ToolDefinition]:
        self.session.add(
            ToolUsageEvent(
                tool_id=tool_id,
                user_id=user_id,
                config_bundle_id=config_bundle_id,
            )
        )
        tool = await self.get_by_id(tool_id)
        if tool is not None:
            tool.tool_selected_freq += 1
        await self.session.flush()
        return tool

    async def add_domain(self, tool: ToolDefinition, domain: KnowledgeDomain) -> ToolDefinition:
        await self.session.refresh(tool, attribute_names=["domains"])
        if domain not in tool.domains:
            tool.domains.append(domain)
        await self.session.flush()
        return tool

    async def list_by_domain(self, domain_id: int) -> list[ToolDefinition]:
        
        result = await self.session.execute(
            select(ToolDefinition)
            .join(ToolDomain, ToolDefinition.id == ToolDomain.tool_id)
            .where(ToolDomain.domain_id == domain_id)
        )
        return list(result.scalars().all())