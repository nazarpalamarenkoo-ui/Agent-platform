from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client import AsyncQdrantClient
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

from src.knowledge.pipeline import IngestionPipeline
from src.knowledge.acquisition.fetch import Fetcher
from src.knowledge.acquisition.search import SearXNG
from src.knowledge.acquisition.orchestration import Orchestrator
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
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
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository

from src.services.user_service import UserService
from src.services.agent_profile_service import AgentProfileService
from src.services.config_bundle_service import ConfigBundleService
from src.services.device_auth_service import DeviceAuthService
from src.services.skill_service import SkillService
from src.services.tool_service import ToolService

_qdrant_client: AsyncQdrantClient | None = None
_embedding: Embedding | None = None
_reranker: Reranker | None = None
_http_client: httpx.AsyncClient | None = None


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


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient()
    return _http_client

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


async def get_vector_store(
    client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> QdrantVectorSearch:
    return await QdrantVectorSearch.create(client, settings.QDRANT_COLLECTION)


async def get_ingestion_pipeline(
    vector_store: QdrantVectorSearch = Depends(get_vector_store),
    document_repo: DocumentRepository = Depends(get_document_repo),
    chunk_repo: DocumentChunkRepository = Depends(get_chunk_repo),
    pack_repo: KnowledgePackRepository = Depends(get_pack_repo)
) -> IngestionPipeline:
    return IngestionPipeline(
        vector_store=vector_store,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        pack_repo = pack_repo
    )


async def get_retrieval(
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


async def get_orchestrator(
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> Orchestrator:
    searxng = SearXNG(base_url=settings.SEARXNG_URL, client=http_client)
    fetcher = Fetcher(client=http_client)
    return Orchestrator(search_engine=searxng, fetcher=fetcher)


async def get_knowledge_service(
    ingestion_pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    retrieval: HybridRetrieval = Depends(get_retrieval),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    document_repo: DocumentRepository = Depends(get_document_repo),
    tag_repo: TagRepository = Depends(get_tag_repo),
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo),
    config_bundle_repo: ConfigBundleRepository = Depends(get_config_bundle_repo)
) -> KnowledgeService:
    return KnowledgeService(
        orchestrator=orchestrator,
        ingestion_pipeline=ingestion_pipeline,
        retrieval=retrieval,
        document_repo=document_repo,
        tag_repo=tag_repo,
        knowledge_domain_repo=domain_repo,
        config_bundle_repo=config_bundle_repo
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
        knowledge_pack_repo= knowledge_pack_repo,
        agent_profile_repo=agent_repo
    )

async def get_device_auth_service(
    device_code_repo: DeviceCodeRepository = Depends(get_device_code_repo),
) -> DeviceAuthService:
    return DeviceAuthService(device_code_repo=device_code_repo)

async def get_skill_service(
    skill_repo: SkillRepository = Depends(get_skill_repo),
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo),
) -> SkillService:
    return SkillService(skill_repo=skill_repo, domain_repo=domain_repo)

async def get_tool_service(
    tool_repo: ToolDefinitionRepository = Depends(get_tool_repo),
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo)
) -> ToolService:
    return ToolService(tool_repo=tool_repo, domain_repo=domain_repo)

async def get_domain_service(
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo)
) -> DomainService:
    return DomainService(domain_repo=domain_repo)

async def get_knowledge_pack_service(
    pack_repo: KnowledgePackRepository = Depends(get_pack_repo), 
    domain_repo: KnowledgeDomainRepository = Depends(get_domain_repo)
) -> KnowledgePackService:
    return KnowledgePackService(pack_repo=pack_repo, domain_repo=domain_repo)