from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.document import Document
from src.db.models.tags import Tag
from src.db.enums.document_status import DocumentStatus
from src.repositories.base_repo import BaseRepository


class DocumentRepository(BaseRepository[Document]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, Document)

    async def get_by_source(self, source: str) -> list[Document]:
        result = await self.session.execute(
            select(Document).where(Document.source == source)
        )
        return list(result.scalars().all())

    async def get_by_hash(self, content_hash: str) -> Optional[Document]:
        result = await self.session.execute(
            select(Document).where(Document.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def get_pending(self, limit: int = 50) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(Document.status == DocumentStatus.PENDING)
            .order_by(Document.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_domain(self, domain_id: int) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .options(selectinload(Document.tags))
            .where(Document.domain_id == domain_id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def update_status(self, document_id: int, status: DocumentStatus) -> Document:
        document = await self.get_by_id(document_id)

        if document is None:
            raise FileNotFoundError(document_id)

        document.status = status

        await self.session.flush()
        return document

    async def assign_domain(self, document_id: int, domain_id: int) -> Document:
        document = await self.get_by_id(document_id)

        if document is None:
            raise FileNotFoundError(document_id)

        document.domain_id = domain_id
        await self.session.flush()
        return document

    async def add_tag(self, document: Document, tags: list[Tag]) -> Document:
        await self.session.refresh(document, attribute_names=["tags"])

        existing_ids = {tag.id for tag in document.tags}

        for tag in tags:
            if tag.id not in existing_ids:
                document.tags.append(tag)

        await self.session.flush()
        return document