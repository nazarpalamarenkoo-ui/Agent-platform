import httpx
from qdrant_client import AsyncQdrantClient

from src.catalog.draft.generator import SkillDraftGenerator
from src.config import settings
from src.db.db_connection import AsyncSessionLocal
from src.knowledge.acquisition.dedup.deduplicator import Deduplicator
from src.knowledge.acquisition.discovery.discovery import Discovery
from src.knowledge.acquisition.discovery.query_builder import QueryBuilder
from src.knowledge.acquisition.discovery.result_parser import ResultParser
from src.knowledge.acquisition.fetch import Fetcher
from src.knowledge.acquisition.judge.decision_engine import DecisionEngine
from src.knowledge.acquisition.judge.judge_llm_client import JudgeLLMClient
from src.knowledge.acquisition.judge.judge_persistence import JudgePersistence
from src.knowledge.acquisition.judge.llm_judge import LLMJudge
from src.knowledge.acquisition.orchestration import Orchestrator
from src.knowledge.acquisition.preview_fetcher.preview_fetrcher import PreviewFetcher
from src.knowledge.acquisition.ranking.ranker import Ranker
from src.knowledge.acquisition.search import SearXNG
from src.knowledge.corpus.builder import CorpusBuilder
from src.knowledge.pipeline import IngestionPipeline
from src.rag.embeddings.bge_m3 import Embedding
from src.rag.retrieval.agentic.llm_client import LLMClient
from src.rag.storage.vector_store import QdrantVectorSearch
from src.repositories.discovered_document_repo import DiscoveredDocumentRepository
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.repositories.document_repo import DocumentRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.session_per_call import per_call


async def build_corpus_builder(
    *,
    qdrant: AsyncQdrantClient,
    embedding: Embedding,
    http: httpx.AsyncClient,
    fetch_http: httpx.AsyncClient,
    judge_client: JudgeLLMClient,
) -> CorpusBuilder:
    document_repo = per_call(DocumentRepository, AsyncSessionLocal)
    chunk_repo = per_call(DocumentChunkRepository, AsyncSessionLocal)
    pack_repo = per_call(KnowledgePackRepository, AsyncSessionLocal)
    discovered_repo = per_call(DiscoveredDocumentRepository, AsyncSessionLocal)

    vector_store = await QdrantVectorSearch.create(qdrant, settings.QDRANT_COLLECTION)
    pipeline = IngestionPipeline(
        vector_store=vector_store,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        pack_repo=pack_repo,
        embedder=embedding,
    )

    fetcher = Fetcher(client=fetch_http)
    searxng = SearXNG(base_url=settings.SEARXNG_URL, client=http)
    discovery = Discovery(
        search_engine=searxng,
        parser=ResultParser(),
        max_results_per_query=settings.DISCOVERY_MAX_RESULTS_PER_QUERY,
    )
    orchestrator = Orchestrator(
        fetcher=fetcher,
        query_builder=QueryBuilder(),
        discovery=discovery,
        deduplicator=Deduplicator(discover_doc=discovered_repo),
        ranker=Ranker(top_n=settings.RANKER_TOP_N),
        preview_fetcher=PreviewFetcher(fetcher=fetcher),
        llm_judge=LLMJudge(client=judge_client, batch_size=settings.JUDGE_BATCH_SIZE),
        decision_engine=DecisionEngine(
            acceptance_threshold=settings.JUDGE_ACCEPTANCE_THRESHOLD
        ),
        judge_persistence=JudgePersistence(repo=discovered_repo),
    )

    return CorpusBuilder(
        pipeline=pipeline,
        orchestrator=orchestrator,
        document_repo=document_repo,
    )


def build_llm_client() -> LLMClient:
    return LLMClient(api_key=settings.MODEL_API_KEY)


def build_draft_generator(*, llm_client: LLMClient) -> SkillDraftGenerator:
    return SkillDraftGenerator(llm_client=llm_client)