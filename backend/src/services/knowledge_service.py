import logging

from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.knowledge.corpus.builder import CorpusBuilder
from src.knowledge.documents_schema.corpus_build_result import CorpusBuilderResult
from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.retrieval.agentic.models import AgenticContext
from src.rag.retrieval.retrieval import Retrieval
from src.rag.storage.base_vector_store import VectorSearchResult
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.tag_repo import TagRepository

logger = logging.getLogger(__name__)


class KnowledgeService:

    def __init__(
        self,
        corpus_builder: CorpusBuilder,
        retrieval: Retrieval,
        tag_repo: TagRepository,
        knowledge_domain_repo: KnowledgeDomainRepository,
        config_bundle_repo: ConfigBundleRepository,
    ):
        self.corpus_builder = corpus_builder
        self.retrieval = retrieval
        self.tag_repo = tag_repo
        self.domain_repo = knowledge_domain_repo
        self.config_bundle_repo = config_bundle_repo

    async def ingest_file(
        self,
        source: str,
        document_type: DocumentType,
        knowledge_type: KnowledgeType,
        knowledge_pack_id: int,
    ) -> CorpusBuilderResult:
        return await self.corpus_builder.build_from_path(
            source_paths=[source],
            knowledge_pack_id=knowledge_pack_id,
            document_type=document_type,
            knowledge_type=knowledge_type,
        )

    async def ingest_from_web(
        self,
        query: str,
        document_type: DocumentType,
        knowledge_type: KnowledgeType,
        knowledge_pack_id: int,
    ) -> CorpusBuilderResult:
        return await self.corpus_builder.build_from_search(
            query=query,
            knowledge_pack_id=knowledge_pack_id,
            document_type=document_type,
            knowledge_type=knowledge_type,
        )

    async def _resolve_pack_slugs(self, config_bundle_id: int) -> list[str]:
        config = await self.config_bundle_repo.get_unscoped_with_relations(config_bundle_id)
        if config is None:
            raise ValueError(f"ConfigBundle with id={config_bundle_id} does not exist")

        return [pack.slug for pack in config.knowledge_packs]

    async def search(
        self,
        query: str,
        limit: int,
        top_n: int,
        k: int,
        config_bundle_id: int,
    ) -> list[VectorSearchResult]:

        pack_slugs = await self._resolve_pack_slugs(config_bundle_id)

        if not pack_slugs:
            return []

        filters = SearchFilter(knowledge_packs=pack_slugs)
        return await self.retrieval.retrieve_hybrid(query, limit, top_n, k, filters)

    async def search_agentic(
        self,
        query: str,
        config_bundle_id: int,
    ) -> AgenticContext | None:

        pack_slugs = await self._resolve_pack_slugs(config_bundle_id)

        if not pack_slugs:
            return None

        return await self.retrieval.retrieve_agentic(query, knowledge_packs=pack_slugs)
    
    async def search_by_slugs(
        self,
        query: str,
        slugs: list[str],
        limit: int,
        top_n: int,
        k: int,
    ) -> list[VectorSearchResult]:
        if not slugs:
            return []
        filters = SearchFilter(knowledge_packs=list(slugs))
        return await self.retrieval.retrieve_hybrid(query, limit, top_n, k, filters)