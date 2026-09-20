import asyncio
import hashlib
from datetime import datetime, timezone

from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.acquisition.search import SearXNG
from src.knowledge.acquisition.fetch import Fetcher


class Orchestrator:

    def __init__(self, search_engine: SearXNG, fetcher: Fetcher):
        self.search_engine = search_engine
        self.fetcher = fetcher

    async def orchestrate(self, query: str, limit: int = 5) -> list[RawDocument]:
        search_results = await self.search_engine.search(query, limit=limit)

        if not search_results:
            return []

        fetch_tasks = [self.fetcher.fetch(r.url) for r in search_results]
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        return [
            RawDocument(
                source=r.source,
                content=r.content,
                content_type=r.content_type,
                content_hash=hashlib.sha256(r.content).hexdigest(),
                fetched_at=datetime.now(timezone.utc)
            )
            for r in results
            if isinstance(r, RawDocument)
        ]