from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.tags import Tag
from src.repositories.base_repo import BaseRepository


class TagRepository(BaseRepository[Tag]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, Tag)

    async def get_by_name(self, tag_name: str) -> Optional[Tag]:
        result = await self.session.execute(
            select(Tag).where(Tag.tag_name == tag_name)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, tag_name: str) -> Tag:
        normalized = tag_name.strip().lower()
        tag = await self.get_by_name(normalized)
        if tag is not None:
            return tag
        return await self.create(tag_name=normalized)