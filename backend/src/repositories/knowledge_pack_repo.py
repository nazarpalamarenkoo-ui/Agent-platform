from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload, selectinload

from src.repositories.base_repo import BaseRepository
from src.db.models.knowledge_packs import KnowledgePack
from src.db.models.config_bundle_knowledge_packs import ConfigBundleKnowledgePack


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
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_active(
        self, limit: int = 100, offset: int = 0, domain_id: int | None = None
    ) -> list[KnowledgePack]:
        stmt = select(KnowledgePack).where(KnowledgePack.archived_at.is_(None))
        if domain_id is not None:
            stmt = stmt.where(KnowledgePack.domain_id == domain_id)
        stmt = (
            stmt.options(raiseload(KnowledgePack.documents))
            .order_by(KnowledgePack.name, KnowledgePack.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_candidates(self):
        result = await self.session.execute(
            select(KnowledgePack.id, KnowledgePack.name, KnowledgePack.description)
            .where(KnowledgePack.archived_at.is_(None))
            .order_by(KnowledgePack.id)
        )
        return list(result.all())

    async def get_active(self, pack_id: int) -> Optional[KnowledgePack]:
        result = await self.session.execute(
            select(KnowledgePack)
            .options(raiseload(KnowledgePack.documents))
            .where(KnowledgePack.id == pack_id, KnowledgePack.archived_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_active_many(self, pack_ids: Sequence[int]) -> list[KnowledgePack]:
        ids = list(set(pack_ids))
        if not ids:
            return []
        result = await self.session.execute(
            select(KnowledgePack)
            .options(raiseload(KnowledgePack.documents))
            .where(KnowledgePack.id.in_(ids), KnowledgePack.archived_at.is_(None))
        )
        return list(result.scalars().all())

    async def list_for_bundle(self, bundle_id: int) -> list[KnowledgePack]:
        result = await self.session.execute(
            select(KnowledgePack)
            .options(raiseload(KnowledgePack.documents))
            .join(
                ConfigBundleKnowledgePack,
                ConfigBundleKnowledgePack.knowledge_pack_id == KnowledgePack.id,
            )
            .where(ConfigBundleKnowledgePack.config_bundle_id == bundle_id)
            .order_by(KnowledgePack.id)
        )
        return list(result.scalars().all())

    async def list_slugs_for_bundle(self, bundle_id: int) -> list[str]:
        result = await self.session.execute(
            select(KnowledgePack.slug)
            .join(
                ConfigBundleKnowledgePack,
                ConfigBundleKnowledgePack.knowledge_pack_id == KnowledgePack.id,
            )
            .where(ConfigBundleKnowledgePack.config_bundle_id == bundle_id)
            .order_by(KnowledgePack.slug)
        )
        return list(result.scalars().all())

    async def list_manifest_for_bundle(self, bundle_id: int):
        result = await self.session.execute(
            select(
                KnowledgePack.id,
                KnowledgePack.slug,
                KnowledgePack.version,
                KnowledgePack.archived_at,
            )
            .join(
                ConfigBundleKnowledgePack,
                ConfigBundleKnowledgePack.knowledge_pack_id == KnowledgePack.id,
            )
            .where(ConfigBundleKnowledgePack.config_bundle_id == bundle_id)
            .order_by(KnowledgePack.id)
        )
        return list(result.all())

    async def archive(self, pack: KnowledgePack) -> KnowledgePack:
        if pack.archived_at is None:
            pack.archived_at = datetime.now(timezone.utc)
            await self.session.flush()
        return pack

    async def restore(self, pack: KnowledgePack) -> KnowledgePack:
        if pack.archived_at is not None:
            pack.archived_at = None
            await self.session.flush()
        return pack