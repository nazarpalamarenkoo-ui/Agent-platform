from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.document_chunks import DocumentChunk
from src.repositories.base_repo import BaseRepository


class DocumentChunkRepository(BaseRepository[DocumentChunk]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, DocumentChunk)

    async def get_by_document(self, document_id: int) -> list[DocumentChunk]:
        result = await self.session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def bulk_create(self, chunks: list[dict]) -> list[DocumentChunk]:
        entities = [DocumentChunk(**data) for data in chunks]
        self.session.add_all(entities)
        await self.session.flush()
        return entities

    async def delete_for_document(self, document_id: int) -> None:
        for chunk in await self.get_by_document(document_id):
            await self.session.delete(chunk)
        await self.session.flush()