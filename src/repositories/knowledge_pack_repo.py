from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.repositories.base_repo import BaseRepository
from src.db.models.knowledge_packs import KnowledgePack


class KnowledgePackRepository(BaseRepository[KnowledgePack]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, KnowledgePack)

    async def get_by_slug(self, slug: str) -> Optional[KnowledgePack]:
        result = await self.session.execute(
            select(KnowledgePack).where(KnowledgePack.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_by_slugs(self, slugs: list[str]) -> list[KnowledgePack]:
        result = await self.session.execute(
            select(KnowledgePack).where(KnowledgePack.slug.in_(slugs))
        )
        return list(result.scalars().all())

    async def get_by_name_in_domain(self, domain_id: int, name: str) -> Optional[KnowledgePack]:
        result = await self.session.execute(
            select(KnowledgePack).where(
                KnowledgePack.domain_id == domain_id,
                KnowledgePack.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_domain(self, domain_id: int) -> list[KnowledgePack]:
        result = await self.session.execute(
            select(KnowledgePack).where(KnowledgePack.domain_id == domain_id)
        )
        return list(result.scalars().all())

    async def get_by_id_with_documents(self, pack_id: int) -> Optional[KnowledgePack]:
        result = await self.session.execute(
            select(KnowledgePack)
            .options(selectinload(KnowledgePack.documents))
            .where(KnowledgePack.id == pack_id)
        )
        return result.scalar_one_or_none()