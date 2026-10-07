import asyncio
import itertools
import logging
from src.knowledge.acquisition.search import SearXNG, SearXNGUnavailableError
from src.knowledge.documents_schema.discovery_model import DiscoveryResult
from src.knowledge.acquisition.discovery.result_parser import ResultParser

logger = logging.getLogger(__name__)

class Discovery:
    
    def __init__(self, search_engine: SearXNG, parser: ResultParser, max_results_per_query: int):
        
        self.search_engine = search_engine
        self.parser = parser
        self.max_results_per_query = max_results_per_query
        
    async def _search_one(self, strategy: str) -> list[DiscoveryResult]:
        try:
            raw_results = await self.search_engine.search(strategy, limit=self.max_results_per_query)
        except SearXNGUnavailableError:
            logger.warning(f"SearXNG unavailable for strategy '{strategy}'")
            return []

        return self.parser.parse_many(raw_results)
        
    def _deduplicate_by_url(self, results: list[DiscoveryResult]) -> list[DiscoveryResult]:
        seen: set[str] = set()
        unique = []

        for result in results:
            normalized_url = result.url.rstrip("/").lower()
            if normalized_url in seen:
                continue
            seen.add(normalized_url)
            unique.append(result)

        return unique
    
    async def search_many(self, strategies: list[str]) -> list[DiscoveryResult]:
        if not strategies:
            return []

        results_per_strategy = await asyncio.gather(*[self._search_one(s) for s in strategies])

        flat_results = list(itertools.chain.from_iterable(results_per_strategy))

        return self._deduplicate_by_url(flat_results)