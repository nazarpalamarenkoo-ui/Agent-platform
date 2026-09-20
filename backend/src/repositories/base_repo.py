from typing import Generic, TypeVar, Type, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.db_connection import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):

    def __init__(self, session: AsyncSession, model: Type[ModelType]) -> None:
        self.session = session
        self.model = model

    async def get_by_id(self, entity_id: int) -> ModelType | None:
        result = await self.session.execute(
            select(self.model).where(self.model.id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelType]:
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def create(self, **kwargs) -> ModelType:
        entity = self.model(**kwargs)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: ModelType, **kwargs) -> ModelType:
        for key, value in kwargs.items():
            setattr(entity, key, value)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelType) -> None:
        await self.session.delete(entity)
        await self.session.flush()