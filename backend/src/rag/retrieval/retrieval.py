from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.retrieval.agentic.context_builder import ContextBuilder
from src.rag.retrieval.agentic.models import AgenticContext
from src.rag.retrieval.agentic.orchestrator import AgenticOrchestrator
from src.rag.retrieval.hybrid_retrieval import HybridRetrieval
from src.rag.storage.base_vector_store import VectorSearchResult


class Retrieval:

    def __init__(
        self,
        hybrid: HybridRetrieval,
        agentic: AgenticOrchestrator,
        context_builder: ContextBuilder,
    ):
        self.hybrid = hybrid
        self.agentic = agentic
        self.context_builder = context_builder

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
        raw_context = await self.agentic.retrieve(
            query=query,
            knowledge_packs=knowledge_packs,
        )

        cleaned_evidence = self.context_builder.build_evidence_list(raw_context.evidence)

        return AgenticContext(
            original_query=raw_context.original_query,
            plan=raw_context.plan,
            evidence=cleaned_evidence,
            evaluation=raw_context.evaluation,
            iteration=raw_context.iteration,
            iterations=raw_context.iterations,
        )