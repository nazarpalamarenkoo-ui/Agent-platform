from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.tool_usage_events import ToolUsageEvent
from src.repositories.base_repo import BaseRepository


class ToolUsageEventRepository(BaseRepository[ToolUsageEvent]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, ToolUsageEvent)

    async def get_for_tool(self, tool_id: int, limit: int = 100) -> list[ToolUsageEvent]:
        result = await self.session.execute(
            select(ToolUsageEvent)
            .where(ToolUsageEvent.tool_id == tool_id)
            .order_by(ToolUsageEvent.selected_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_for_config_bundle(self, config_bundle_id: int) -> list[ToolUsageEvent]:
        result = await self.session.execute(
            select(ToolUsageEvent)
            .options(selectinload(ToolUsageEvent.tool))
            .where(ToolUsageEvent.config_bundle_id == config_bundle_id)
            .order_by(ToolUsageEvent.selected_at.desc())
        )
        return list(result.scalars().all())