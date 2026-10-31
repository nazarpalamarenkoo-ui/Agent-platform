from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.skill_access_logs import SkillAccessLog


class SkillAccessLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(self, admin_id, owner_id, action, skill_id=None, note=None):
        entry = SkillAccessLog(
            admin_id=admin_id, owner_id=owner_id, skill_id=skill_id,
            action=action, note=note,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_for_owner(self, owner_id: int, limit: int = 100, offset: int = 0):
        result = await self.session.execute(
            select(SkillAccessLog)
            .where(SkillAccessLog.owner_id == owner_id)
            .order_by(SkillAccessLog.created_at.desc(), SkillAccessLog.id.desc())
            .limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def list_all(self, limit: int = 100, offset: int = 0):
        result = await self.session.execute(
            select(SkillAccessLog)
            .order_by(SkillAccessLog.created_at.desc(), SkillAccessLog.id.desc())
            .limit(limit).offset(offset)
        )
        return list(result.scalars().all())