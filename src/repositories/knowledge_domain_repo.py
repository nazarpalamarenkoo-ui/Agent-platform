from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.knowledge_domains import KnowledgeDomain
from src.repositories.base_repo import BaseRepository


class KnowledgeDomainRepository(BaseRepository[KnowledgeDomain]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, KnowledgeDomain)

    async def get_by_slug(self, slug: str) -> Optional[KnowledgeDomain]:
        result = await self.session.execute(
            select(KnowledgeDomain).where(KnowledgeDomain.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_root_domains(self) -> list[KnowledgeDomain]:
        result = await self.session.execute(
            select(KnowledgeDomain)
            .options(selectinload(KnowledgeDomain.children))
            .where(KnowledgeDomain.parent_domain_id.is_(None))
        )
        return list(result.scalars().all())