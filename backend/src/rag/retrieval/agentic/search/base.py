from typing import Protocol

from src.rag.storage.base_vector_store import VectorSearchResult


class Searcher(Protocol):
    """Minimal contract Orchestrator needs from the search layer.

    Orchestrator depends only on this abstraction, never on a concrete
    search implementation (HybridRetrieval, a future dense-only searcher,
    a test double, etc.) - that's decided at the build_retrieval() level,
    same as with BasePlanner/BaseEvaluator.
    """

    async def search(self, query: str) -> list[VectorSearchResult]:
        ...