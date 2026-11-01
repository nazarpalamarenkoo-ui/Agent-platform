from typing import AsyncGenerator
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client import AsyncQdrantClient
from arq.connections import ArqRedis
import httpx

from src.config import settings
from src.db.db_connection import get_db

from src.rag.retrieval.query_encoder import QueryEncoder
from src.repositories.document_repo import DocumentRepository
from src.repositories.document_chunk_repo import DocumentChunkRepository

from src.rag.storage.vector_store import QdrantVectorSearch
from src.rag.embeddings.bge_m3 import Embedding
from src.rag.retrieval.dense_search import DenseSearch
from src.rag.retrieval.sparse_search import SparseSearch
from src.rag.retrieval.rrf import RRF
from src.rag.retrieval.reranker import Reranker
from src.rag.retrieval.hybrid_retrieval import HybridRetrieval
from src.rag.retrieval.retrieval import Retrieval

from src.rag.retrieval.agentic.llm_client import LLMClient
from src.rag.retrieval.agentic.planner.base import BasePlanner
from src.rag.retrieval.agentic.planner.heuristic_planner import HeuristicPlanner
from src.rag.retrieval.agentic.planner.llm_planner import LLMPlanner
from src.rag.retrieval.agentic.evaluator.base import BaseEvaluator
from src.rag.retrieval.agentic.evaluator.heuristic_evaluator import HeuristicEvaluator
from src.rag.retrieval.agentic.evaluator.llm_evaluator import LLMEvaluator
from src.rag.retrieval.agentic.search.hybrid_search_adapter import HybridSearchAdapter
from src.rag.retrieval.agentic.orchestrator import AgenticOrchestrator
from src.rag.retrieval.agentic.context_builder import ContextBuilder
from src.knowledge.corpus.builder import CorpusBuilder
from src.catalog.hint.candidate_collector import CandidateCollector
from src.catalog.hint.catalog_hint_service import CatalogHintService

from src.knowledge.pipeline import IngestionPipeline
from src.knowledge.acquisition.fetch import Fetcher
from src.knowledge.acquisition.search import SearXNG
from src.knowledge.acquisition.orchestration import Orchestrator
from src.knowledge.acquisition.discovery.query_builder import QueryBuilder
from src.knowledge.acquisition.discovery.discovery import Discovery
from src.knowledge.acquisition.discovery.result_parser import ResultParser
from src.knowledge.acquisition.dedup.deduplicator import Deduplicator
from src.knowledge.acquisition.ranking.ranker import Ranker
from src.knowledge.acquisition.preview_fetcher.preview_fetrcher import PreviewFetcher
from src.knowledge.acquisition.judge.judge_llm_client import JudgeLLMClient
from src.knowledge.acquisition.judge.llm_judge import LLMJudge
from src.knowledge.acquisition.judge.decision_engine import DecisionEngine
from src.knowledge.acquisition.judge.judge_persistence import JudgePersistence

from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.discovered_document_repo import DiscoveredDocumentRepository
from src.services.domain_service import DomainService
from src.services.knowledge_pack_service import KnowledgePackService
from src.services.knowledge_service import KnowledgeService

from src.repositories.tag_repo import TagRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository

from src.repositories.user_repo import UserRepository
from src.repositories.token_usage_event_repo import TokenUsageEventRepository
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.device_code_repo import DeviceCodeRepository
from src.repositories.notification_repo import NotificationRepository
from src.repositories.background_job_repo import BackgroundJobRepository

from src.catalog.draft.planner import DraftPlanner
from src.repositories.skill_access_log_repo import SkillAccessLogRepository
from src.services.admin_user_content_service import AdminUserContentService
from src.services.user_tool_service import UserToolService
from src.services.user_service import UserService
from src.services.agent_profile_service import AgentProfileService
from src.services.config_bundle_service import ConfigBundleService
from src.services.effective_bundle_service import EffectiveBundleService
from src.services.bundle_export_service import BundleExportService
from src.services.device_auth_service import DeviceAuthService
from src.services.notification_service import NotificationService
from src.services.user_skill_service import UserSkillService
from src.services.skill_draft_service import SkillDraftService
from src.services.skill_service import SkillService
from src.services.tool_service import ToolService

_qdrant_client: AsyncQdrantClient | None = None
_embedding: Embedding | None = None
_reranker: Reranker | None = None
_http_client: httpx.AsyncClient | None = None
_fetch_http_client: httpx.AsyncClient | None = None
_llm_client: LLMClient | None = None
_judge_llm_client: JudgeLLMClient | None = None


async def get_qdrant_client() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(url=settings.QDRANT_URL)
    return _qdrant_client


async def get_embedding() -> Embedding:
    global _embedding
    if _embedding is None:
        _embedding = Embedding()
    return _embedding


async def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker


async def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(api_key=settings.MODEL_API_KEY)
    return _llm_client


async def get_judge_llm_client() -> JudgeLLMClient:
    global _judge_llm_client
    if _judge_llm_client is None:
        _judge_llm_client = JudgeLLMClient(
            base_url=settings.JUDGE_BASE_URL,
            model=settings.JUDGE_MODEL,
            api_key=settings.JUDGE_API_KEY,
            timeout=settings.JUDGE_TIMEOUT,
            max_tokens=settings.JUDGE_MAX_TOKENS,
            use_json_schema=settings.JUDGE_USE_JSON_SCHEMA,
        )
    return _judge_llm_client


async def get_context_builder() -> ContextBuilder:
    return ContextBuilder()


async def get_arq_pool(request: Request) -> ArqRedis:
    return request.app.state.arq_pool


async def get_background_job_repo() -> BackgroundJobRepository:
    return BackgroundJobRepository()


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/pdf,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(follow_redirects=True)
    return _http_client


async def get_fetch_http_client() -> httpx.AsyncClient:
    global _fetch_http_client
    if _fetch_http_client is None:
        _fetch_http_client = httpx.AsyncClient(
            follow_redirects=True,
            headers=BROWSER_HEADERS,
        )
    return _fetch_http_client


async def get_user_repo(
    session: AsyncSession = Depends(get_db)
) -> UserRepository:
    return UserRepository(session)


async def get_token_repo(
    session: AsyncSession = Depends(get_db)
) -> TokenUsageEventRepository:
    return TokenUsageEventRepository(session)


async def get_agent_repo(
    session: AsyncSession = Depends(get_db)
) -> AgentProfileRepository:
    return AgentProfileRepository(session)


async def get_config_bundle_repo(
    session: AsyncSession = Depends(get_db)
) -> ConfigBundleRepository:
    return ConfigBundleRepository(session)


async def get_device_code_repo(
    session: AsyncSession = Depends(get_db)
) -> DeviceCodeRepository:
    return DeviceCodeRepository(session)


async def get_skill_repo(
    session: AsyncSession = Depends(get_db)
) -> SkillRepository:
    return SkillRepository(session)


async def get_tool_repo(
    session: AsyncSession = Depends(get_db)
) -> ToolDefinitionRepository:
    return ToolDefinitionRepository(session)


async def get_pack_repo(
    session: AsyncSession = Depends(get_db)
) -> KnowledgePackRepository:
    return KnowledgePackRepository(session)


async def get_notification_repo(
    session: AsyncSession = Depends(get_db)
) -> NotificationRepository:
    return NotificationRepository(session)


async def get_document_repo(
    session: AsyncSession = Depends(get_db),
) -> DocumentRepository:
    return DocumentRepository(session)


async def get_chunk_repo(
    session: AsyncSession = Depends(get_db),
) -> DocumentChunkRepository:
    return DocumentChunkRepository(session)


async def get_tag_repo(
    session: AsyncSession = Depends(get_db),
) -> TagRepository:
    return TagRepository(session)


async def get_domain_repo(
    session: AsyncSession = Depends(get_db),
) -> KnowledgeDomainRepository:
    return KnowledgeDomainRepository(session)


async def get_discovered_document_repo(
    session: AsyncSession = Depends(get_db),
) -> DiscoveredDocumentRepository:
    return DiscoveredDocumentRepository(session)


async def get_vector_store(
    client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> QdrantVectorSearch:
    return await QdrantVectorSearch.create(client, settings.QDRANT_COLLECTION)


async def get_hybrid_retrieval(
    embedding: Embedding = Depends(get_embedding),
    vector_store: QdrantVectorSearch = Depends(get_vector_store),
    reranker: Reranker = Depends(get_reranker),
) -> HybridRetrieval:
    query_encoder = QueryEncoder(embedding)
    dense = DenseSearch(vector_store=vector_store)
    sparse = SparseSearch(vector_store=vector_store)
    rrf = RRF()
    return HybridRetrieval(
        query_encoder=query_encoder,
        dense_search=dense,
        sparse_search=sparse,
        rrf=rrf,
        reranker=reranker,
    )


async def get_ingestion_pipeline(
    vector_store: QdrantVectorSearch = Depends(get_vector_store),
    document_repo: DocumentRepository = Depends(get_document_repo),
    chunk_repo: DocumentChunkRepository = Depends(get_chunk_repo),
    pack_repo: KnowledgePackRepository = Depends(get_pack_repo),
    embedding: Embedding = Depends(get_embedding),
) -> IngestionPipeline:
    return IngestionPipeline(
        vector_store=vector_store,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        pack_repo=pack_repo,
        embedder=embedding,
    )


async def get_planner(
    llm_client: LLMClient = Depends(get_llm_client),
) -> BasePlanner:
    if settings.AGENTIC_STRATEGY == "heuristic":
        return HeuristicPlanner()
    return LLMPlanner(llm_client=llm_client)


async def get_evaluator(
    llm_client: LLMClient = Depends(get_llm_client),
) -> BaseEvaluator:
    if settings.AGENTIC_STRATEGY == "heuristic":
        return HeuristicEvaluator()
    return LLMEvaluator(llm_client=llm_client)


async def get_agentic_orchestrator(
    planner: BasePlanner = Depends(get_planner),
    evaluator: BaseEvaluator = Depends(get_evaluator),
    hybrid_retrieval: HybridRetrieval = Depends(get_hybrid_retrieval),
) -> AgenticOrchestrator:
    searcher = HybridSearchAdapter(hybrid_retrieval=hybrid_retrieval)
    return AgenticOrchestrator(
        planner=planner,
        evaluator=evaluator,
        searcher=searcher,
    )


async def get_retrieval(
    hybrid_retrieval: HybridRetrieval = Depends(get_hybrid_retrieval),
    agentic_orchestrator: AgenticOrchestrator = Depends(get_agentic_orchestrator),
    context_builder: ContextBuilder = Depends(get_context_builder),
) -> Retrieval:
    return Retrieval(
        hybrid=hybrid_retrieval,
        agentic=agentic_orchestrator,
        context_builder=context_builder,
    )


async def get_searxng(
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> SearXNG:
    return SearXNG(base_url=settings.SEARXNG_URL, client=http_client)


async def get_fetcher(
    http_client: httpx.AsyncClient = Depends(get_fetch_http_client),
) -> Fetcher:
    return Fetcher(client=http_client)


async def get_query_builder() -> QueryBuilder:
    return QueryBuilder()


async def get_result_parser() -> ResultParser:
    return ResultParser()


async def get_discovery(
    searxng: SearXNG = Depends(get_searxng),
    parser: ResultParser = Depends(get_result_parser),
) -> Discovery:
    return Discovery(
        search_engine=searxng,
        parser=parser,
        max_results_per_query=settings.DISCOVERY_MAX_RESULTS_PER_QUERY,
    )


async def get_deduplicator(
    discovered_repo: DiscoveredDocumentRepository = Depends(get_discovered_document_repo),
) -> Deduplicator:
    return Deduplicator(discover_doc=discovered_repo)


async def get_ranker() -> Ranker:
    return Ranker(top_n=settings.RANKER_TOP_N)


async def get_preview_fetcher(
    fetcher: Fetcher = Depends(get_fetcher),
) -> PreviewFetcher:
    return PreviewFetcher(fetcher=fetcher)


async def get_llm_judge(
    judge_client: JudgeLLMClient = Depends(get_judge_llm_client),
) -> LLMJudge:
    return LLMJudge(client=judge_client, batch_size=settings.JUDGE_BATCH_SIZE)


async def get_decision_engine() -> DecisionEngine:
    return DecisionEngine(acceptance_threshold=settings.JUDGE_ACCEPTANCE_THRESHOLD)


async def get_judge_persistence(
    discovered_repo: DiscoveredDocumentRepository = Depends(get_discovered_document_repo),
) -> JudgePersistence:
    return JudgePersistence(repo=discovered_repo)


async def get_orchestrator(
    fetcher: Fetcher = Depends(get_fetcher),
    query_builder: QueryBuilder = Depends(get_query_builder),
    discovery: Discovery = Depends(get_discovery),
    deduplicator: Deduplicator = Depends(get_deduplicator),
    ranker: Ranker = Depends(get_ranker),
    preview_fetcher: PreviewFetcher = Depends(get_preview_fetcher),
    llm_judge: LLMJudge = Depends(get_llm_judge),
    decision_engine: DecisionEngine = Depends(get_decision_engine),
    judge_persistence: JudgePersistence = Depends(get_judge_persistence),
) -> Orchestrator:
    return Orchestrator(
        fetcher=fetcher,
        query_builder=query_builder,
        discovery=discovery,
        deduplicator=deduplicator,
        ranker=ranker,
        preview_fetcher=preview_fetcher,
        llm_judge=llm_judge,
        decision_engine=decision_engine,
        judge_persistence=judge_persistence,
    )


async def get_corpus_builder(
    ingestion_pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    document_repo: DocumentRepository = Depends(get_document_repo),
) -> CorpusBuilder:
    return CorpusBuilder(
        pipeline=ingestion_pipeline,
        orchestrator=orchestrator,
        document_repo=document_repo,
    )


async def get_knowledge_service(
    corpus_builder: CorpusBuilder = Depends(get_corpus_builder),
    retrieval: Retrieval = Depends(get_retrieval),
    tag_repo: TagRepository = Depends(get_tag_repo),
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo),
    config_bundle_repo: ConfigBundleRepository = Depends(get_config_bundle_repo),
) -> KnowledgeService:
    return KnowledgeService(
        corpus_builder=corpus_builder,
        retrieval=retrieval,
        tag_repo=tag_repo,
        knowledge_domain_repo=domain_repo,
        config_bundle_repo=config_bundle_repo,
    )


async def get_candidate_collector(
    skill_repo: SkillRepository = Depends(get_skill_repo),
    tool_repo: ToolDefinitionRepository = Depends(get_tool_repo),
    pack_repo: KnowledgePackRepository = Depends(get_pack_repo),
    agent_repo: AgentProfileRepository = Depends(get_agent_repo),
) -> CandidateCollector:
    return CandidateCollector(
        skill_repo=skill_repo,
        tool_repo=tool_repo,
        pack_repo=pack_repo,
        agent_repo=agent_repo,
    )


async def get_catalog_hint_service(
    llm_client: LLMClient = Depends(get_llm_client),
    candidate_collector: CandidateCollector = Depends(get_candidate_collector),
    skill_repo: SkillRepository = Depends(get_skill_repo),
    tool_repo: ToolDefinitionRepository = Depends(get_tool_repo),
    pack_repo: KnowledgePackRepository = Depends(get_pack_repo),
    agent_repo: AgentProfileRepository = Depends(get_agent_repo),
) -> CatalogHintService:
    return CatalogHintService(
        llm_client=llm_client,
        candidate_collector=candidate_collector,
        skill_repo=skill_repo,
        tool_repo=tool_repo,
        pack_repo=pack_repo,
        agent_repo=agent_repo,
    )


async def get_user_service(
    user_repo: UserRepository = Depends(get_user_repo),
    token_repo: TokenUsageEventRepository = Depends(get_token_repo),
) -> UserService:
    return UserService(user_repo=user_repo, token_repo=token_repo)


async def get_agent_profile_service(
    agent_repo: AgentProfileRepository = Depends(get_agent_repo),
    skill_repo: SkillRepository = Depends(get_skill_repo),
    tool_repo: ToolDefinitionRepository = Depends(get_tool_repo),
) -> AgentProfileService:
    return AgentProfileService(
        agent_profile_repo=agent_repo, skill_repo=skill_repo, tool_repo=tool_repo
    )


async def get_config_bundle_service(
    config_bundle_repo: ConfigBundleRepository = Depends(get_config_bundle_repo),
    agent_repo: AgentProfileRepository = Depends(get_agent_repo),
    skill_repo: SkillRepository = Depends(get_skill_repo),
    tool_repo: ToolDefinitionRepository = Depends(get_tool_repo),
    knowledge_pack_repo: KnowledgePackRepository = Depends(get_pack_repo)
) -> ConfigBundleService:
    return ConfigBundleService(
        config_bundle_repo=config_bundle_repo,
        skill_repo=skill_repo,
        tool_repo=tool_repo,
        knowledge_pack_repo=knowledge_pack_repo,
        agent_profile_repo=agent_repo
    )


async def get_effective_bundle_service(
    config_bundle_repo: ConfigBundleRepository = Depends(get_config_bundle_repo),
    agent_repo: AgentProfileRepository = Depends(get_agent_repo),
    skill_repo: SkillRepository = Depends(get_skill_repo),
    tool_repo: ToolDefinitionRepository = Depends(get_tool_repo),
    knowledge_pack_repo: KnowledgePackRepository = Depends(get_pack_repo),
) -> EffectiveBundleService:
    return EffectiveBundleService(
        config_bundle_repo=config_bundle_repo,
        skill_repo=skill_repo,
        tool_repo=tool_repo,
        knowledge_pack_repo=knowledge_pack_repo,
        agent_profile_repo=agent_repo,
    )


async def get_device_auth_service(
    device_code_repo: DeviceCodeRepository = Depends(get_device_code_repo),
) -> DeviceAuthService:
    return DeviceAuthService(device_code_repo=device_code_repo)


async def get_notification_service(
    notification_repo: NotificationRepository = Depends(get_notification_repo),
) -> NotificationService:
    return NotificationService(notification_repo=notification_repo)


async def get_skill_service(
    skill_repo: SkillRepository = Depends(get_skill_repo),
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo),
    config_bundle_repo: ConfigBundleRepository = Depends(get_config_bundle_repo),
    notification_repo: NotificationRepository = Depends(get_notification_repo),
) -> SkillService:
    return SkillService(
        skill_repo=skill_repo,
        domain_repo=domain_repo,
        config_bundle_repo=config_bundle_repo,
        notification_repo=notification_repo,
    )


async def get_tool_service(
    tool_repo: ToolDefinitionRepository = Depends(get_tool_repo),
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo),
    config_bundle_repo: ConfigBundleRepository = Depends(get_config_bundle_repo),
    notification_repo: NotificationRepository = Depends(get_notification_repo),
) -> ToolService:
    return ToolService(
        tool_repo=tool_repo,
        domain_repo=domain_repo,
        config_bundle_repo=config_bundle_repo,
        notification_repo=notification_repo,
    )


async def get_domain_service(
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo)
) -> DomainService:
    return DomainService(domain_repo=domain_repo)


async def get_knowledge_pack_service(
    pack_repo: KnowledgePackRepository = Depends(get_pack_repo),
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo)
) -> KnowledgePackService:
    return KnowledgePackService(pack_repo=pack_repo, domain_repo=domain_repo)

async def get_bundle_export_service(
    config_bundle_repo: ConfigBundleRepository = Depends(get_config_bundle_repo),
    skill_repo: SkillRepository = Depends(get_skill_repo),
    effective_service: EffectiveBundleService = Depends(get_effective_bundle_service),
) -> BundleExportService:
    return BundleExportService(
        config_bundle_repo=config_bundle_repo,
        skill_repo=skill_repo,
        effective_service=effective_service,
    )
    
async def get_user_skill_service(
    skill_repo: SkillRepository = Depends(get_skill_repo),
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo),
) -> UserSkillService:
    return UserSkillService(
        skill_repo=skill_repo,
        domain_repo=domain_repo,
    )
    
async def get_skill_access_log_repo(
    session: AsyncSession = Depends(get_db),
) -> SkillAccessLogRepository:
    return SkillAccessLogRepository(session)

async def get_draft_planner(
    llm_client: LLMClient = Depends(get_llm_client),
    pack_repo: KnowledgePackRepository = Depends(get_pack_repo),
) -> DraftPlanner:
    return DraftPlanner(llm_client=llm_client, pack_repo=pack_repo)

async def get_skill_draft_service(
    job_repo: BackgroundJobRepository = Depends(get_background_job_repo),
    arq_pool: ArqRedis = Depends(get_arq_pool),
    bundle_service: ConfigBundleService = Depends(get_config_bundle_service),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
    user_skill_service: UserSkillService = Depends(get_user_skill_service),
    skill_repo: SkillRepository = Depends(get_skill_repo),
    pack_repo: KnowledgePackRepository = Depends(get_pack_repo),
    planner: DraftPlanner = Depends(get_draft_planner),
) -> SkillDraftService:
    return SkillDraftService(
        job_repo=job_repo,
        arq_pool=arq_pool,
        skill_repo=skill_repo,
        user_skill_service=user_skill_service,
        knowledge_service=knowledge_service,
        bundle_service=bundle_service,
        pack_repo=pack_repo,
        planner=planner,
    )
    
async def get_user_tool_service(
    tool_repo: ToolDefinitionRepository = Depends(get_tool_repo),
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo),
) -> UserToolService:
    return UserToolService(tool_repo=tool_repo, domain_repo=domain_repo)


async def get_admin_user_content_service(
    session: AsyncSession = Depends(get_db),
    user_repo: UserRepository = Depends(get_user_repo),
    skill_repo: SkillRepository = Depends(get_skill_repo),
    tool_repo: ToolDefinitionRepository = Depends(get_tool_repo),
    log_repo: SkillAccessLogRepository = Depends(get_skill_access_log_repo),
    notification_repo: NotificationRepository = Depends(get_notification_repo),
) -> AdminUserContentService:
    return AdminUserContentService(
        session=session,
        user_repo=user_repo,
        skill_repo=skill_repo,
        tool_repo=tool_repo,
        log_repo=log_repo,
        notification_repo=notification_repo,
    )