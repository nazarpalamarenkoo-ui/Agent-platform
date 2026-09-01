from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.base_repo import BaseRepository
from src.db.models.skills import Skill
from src.db.models.skill_usage_events import SkillUsageEvent
from src.db.models.knowledge_domains import KnowledgeDomain


class SkillRepository(BaseRepository[Skill]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, Skill)

    async def record_selection(
        self,
        skill_id: int,
        user_id: int,
        config_bundle_id: int | None = None,
    ) -> Optional[Skill]:
        self.session.add(
            SkillUsageEvent(
                skill_id=skill_id,
                user_id=user_id,
                config_bundle_id=config_bundle_id,
            )
        )
        skill = await self.get_by_id(skill_id)
        if skill is not None:
            skill.skill_selected_freq += 1
        await self.session.flush()
        return skill

    async def get_by_name_and_domain(self, skill_name: str, domain_id: int) -> Optional[Skill]:
        # Skill has a single, required domain_id FK (not a many-to-many).
        result = await self.session.execute(
            select(Skill).where(
                Skill.skill_name == skill_name,
                Skill.domain_id == domain_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_domain(self, domain_id: int) -> list[Skill]:
        result = await self.session.execute(
            select(Skill).where(Skill.domain_id == domain_id)
        )
        return list(result.scalars().all())

    async def change_domain(self, skill: Skill, domain: KnowledgeDomain) -> Skill:
        skill.domain_id = domain.id
        await self.session.flush()
        return skill