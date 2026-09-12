import mimetypes

from src.db.models.document import Document
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.tag_repo import TagRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.document_repo import DocumentRepository
from src.knowledge.pipeline import IngestionPipeline
from src.knowledge.acquisition.orchestration import Orchestrator
from src.knowledge.ingestion.loaders.registry import LoaderRegistry
from src.rag.storage.base_vector_store import VectorSearchResult
from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.retrieval.retrieval import Retrieval
import logging

logger = logging.getLogger(__name__)

class KnowledgeService:
    
    def __init__(
        self,
        orchestrator: Orchestrator,
        ingestion_pipeline: IngestionPipeline,
        retrieval: Retrieval,
        document_repo: DocumentRepository,
        tag_repo: TagRepository,
        knowledge_domain_repo: KnowledgeDomainRepository,    
        config_bundle_repo: ConfigBundleRepository
    ):
        self.orchestrator = orchestrator
        self.ingestion_pipeline = ingestion_pipeline
        self.retrieval = retrieval
        self.document_repo = document_repo
        self.tag_repo = tag_repo
        self.domain_repo = knowledge_domain_repo
        self.config_bundle_repo = config_bundle_repo
        
    async def ingest_file(
        self, 
        source: str, 
        document_type: DocumentType, 
        knowledge_type: KnowledgeType, 
        knowledge_pack_id: int
    ) -> Document:
        
        mime_type, _ = mimetypes.guess_type(source)
        loader = LoaderRegistry.create(mime_type)
        raw_doc = loader.load_document(source)
        
        exists = await self.document_repo.get_by_hash(raw_doc.content_hash)
        
        if exists:
            return exists
        
        return await self.ingestion_pipeline.process(raw_doc, document_type, knowledge_type, knowledge_pack_id)
    
    

    async def ingest_from_web(
        self,
        query: str,
        limit: int,
        document_type: DocumentType,
        knowledge_type: KnowledgeType,
        knowledge_pack_id: int
    ) -> list[Document]:

        raw_docs = await self.orchestrator.orchestrate(query, limit)

        successful_ingestions = []

        for raw_doc in raw_docs:
            try:
                exists = await self.document_repo.get_by_hash(raw_doc.content_hash)
                if exists:
                    continue

                doc = await self.ingestion_pipeline.process(raw_doc, document_type, knowledge_type, knowledge_pack_id)
                successful_ingestions.append(doc)

            except ValueError as e:
                logger.warning("Skipping %s: %s", raw_doc.source, e)
                continue
            except Exception as e:
                logger.exception("Failed to ingest %s", raw_doc.source)
                continue

        return successful_ingestions
    
    async def search(
        self,
        query: str,
        limit: int,
        top_n: int,
        k: int,
        config_bundle_id: int,
    ) -> list[VectorSearchResult]:

        config = await self.config_bundle_repo.get_by_id_with_relations(config_bundle_id)
        if config is None:
            raise ValueError(f"ConfigBundle with id={config_bundle_id} does not exist")
        
        pack_slugs = [pack.slug for pack in config.knowledge_packs]

        if not pack_slugs:
            return []

        filters = SearchFilter(knowledge_packs=pack_slugs)
        return await self.retrieval.retrieve(query, limit, top_n, k, filters)
        
    