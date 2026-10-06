from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.retrieval.hybrid_retrieval import HybridRetrieval
from src.rag.storage.base_vector_store import VectorSearchResult


class HybridSearchAdapter:
    """Adapts HybridRetrieval.retrieve(...) to the Searcher protocol.

    Orchestrator calls search() once per subquery, several times per
    user query (2-5 subqueries, possibly across retry iterations), so
    the defaults here are intentionally smaller than what a single
    top-level HYBRID-mode search would use - keeps per-subquery latency
    (dense+sparse+RRF+reranker) down when it's run repeatedly. Tune
    these based on real latency/quality numbers, not guesswork.
    """

    def __init__(
        self,
        hybrid_retrieval: HybridRetrieval,
        limit: int = 20,
        top_n: int = 5,
        k: int = 60,
        filters: SearchFilter | None = None,
    ):
        self.hybrid_retrieval = hybrid_retrieval
        self.limit = limit
        self.top_n = top_n
        self.k = k
        self.filters = filters

    async def search(self, query: str) -> list[VectorSearchResult]:
        return await self.hybrid_retrieval.retrieve(
            query=query,
            limit=self.limit,
            top_n=self.top_n,
            k=self.k,
            filters=self.filters,
        )