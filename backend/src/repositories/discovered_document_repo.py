from sqlalchemy import select

from src.db.models.discovered_document import DiscoveredDocument
from src.repositories.base_repo import BaseRepository
from src.schemas.discovered_document import DiscoveredDocumentCreate


class DiscoveredDocumentRepository(BaseRepository[DiscoveredDocument]):

    def __init__(self, session):
        super().__init__(session, DiscoveredDocument)

    async def get_existing_url_hashes(self, url_hashes: list[str]) -> set[str]:
        if not url_hashes:
            return set()

        result = await self.session.execute(
            select(DiscoveredDocument.url_hash).where(
                DiscoveredDocument.url_hash.in_(url_hashes)
            )
        )
        return set(result.scalars().all())

    async def save_all(self, records: list[DiscoveredDocumentCreate]) -> None:
        if not records:
            return

        entities = [DiscoveredDocument(**record.model_dump()) for record in records]
        self.session.add_all(entities)
        await self.session.flush()