from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.retrieval.agentic.models import AgenticContext
from src.rag.retrieval.agentic.orchestrator import AgenticOrchestrator
from src.rag.retrieval.hybrid_retrieval import HybridRetrieval
from src.rag.storage.base_vector_store import VectorSearchResult


class Retrieval:

    def __init__(self, hybrid: HybridRetrieval, agentic: AgenticOrchestrator):
        self.hybrid = hybrid
        self.agentic = agentic

    async def retrieve_hybrid(
        self,
        query: str,
        limit: int,
        top_n: int,
        k: int = 60,
        filters: SearchFilter | None = None,
    ) -> list[VectorSearchResult]:
        return await self.hybrid.retrieve(
            query=query,
            limit=limit,
            top_n=top_n,
            k=k,
            filters=filters,
        )

    async def retrieve_agentic(
        self,
        query: str,
        knowledge_packs: list[str],
    ) -> AgenticContext:
        return await self.agentic.retrieve(
            query=query,
            knowledge_packs=knowledge_packs,
        )