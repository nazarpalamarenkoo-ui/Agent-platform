from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.skill_usage_events import SkillUsageEvent
from src.repositories.base_repo import BaseRepository


class SkillUsageEventRepository(BaseRepository[SkillUsageEvent]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, SkillUsageEvent)

    async def get_for_skill(self, skill_id: int, limit: int = 100) -> list[SkillUsageEvent]:
        result = await self.session.execute(
            select(SkillUsageEvent)
            .where(SkillUsageEvent.skill_id == skill_id)
            .order_by(SkillUsageEvent.selected_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_for_config_bundle(self, config_bundle_id: int) -> list[SkillUsageEvent]:
        result = await self.session.execute(
            select(SkillUsageEvent)
            .options(selectinload(SkillUsageEvent.skill))
            .where(SkillUsageEvent.config_bundle_id == config_bundle_id)
            .order_by(SkillUsageEvent.selected_at.desc())
        )
        return list(result.scalars().all())