import mimetypes
from src.db.enums.knowledge_types import KnowledgeType
from src.db.enums.document_type import DocumentType
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.pipeline import IngestionPipeline
from src.knowledge.acquisition.orchestration import Orchestrator
from src.knowledge.documents_schema.corpus_build_result import CorpusBuilderResult
from src.repositories.document_repo import DocumentRepository
from src.knowledge.ingestion.loaders.registry import LoaderRegistry


class CorpusBuilder:
    
    def __init__(self, pipeline: IngestionPipeline, orchestrator: Orchestrator, document_repo: DocumentRepository):
        
        self.pipeline = pipeline
        self.orchestrator = orchestrator
        self.document_repo = document_repo
    
    async def _process_batch(
        self, 
        raw_docs: list[RawDocument], 
        knowledge_pack_id: int, 
        document_type: DocumentType, 
        knowledge_type: KnowledgeType
    )-> CorpusBuilderResult:
        
        succeeded = []
        skipped_duplicates = []
        failed = []
        
        for raw_doc in raw_docs:
            try:
                existing = await self.document_repo.get_by_hash(raw_doc.content_hash)
                if existing is not None:
                    skipped_duplicates.append(raw_doc.source)
                    continue
                
                document = await self.pipeline.process(raw_doc, document_type, knowledge_type, knowledge_pack_id)
                succeeded.append(document.id)
            except Exception as e:
                failed.append({'source': raw_doc.source, 'error': str(e)})
        
        return CorpusBuilderResult(
            succeeded=succeeded,
            skipped_duplicates=skipped_duplicates,
            failed = failed
        )
        
    async def build_from_path(
        self, 
        source_paths: list[str], 
        knowledge_pack_id: int, 
        document_type: DocumentType, 
        knowledge_type: KnowledgeType
    ) -> CorpusBuilderResult:
        
        raw_docs = []
        load_failures = []
        for path in source_paths:
            try:
                content_type, _ = mimetypes.guess_type(path)
                if content_type is None:
                    raise ValueError(f"Could not determine content type for: {path}")
                
                loader = LoaderRegistry.create(content_type)
                raw_docs.append(loader.load_document(path))
            except Exception as e:
                load_failures.append({"source": path, "error": str(e)})
            
        result = await self._process_batch(raw_docs, knowledge_pack_id, document_type, knowledge_type)
        result.failed.extend(load_failures)
        return result
    
    async def build_from_search(self, query: str, limit: int, knowledge_pack_id: int, document_type: DocumentType, knowledge_type: KnowledgeType) -> CorpusBuilderResult:
        
        raw_docs = await self.orchestrator.orchestrate(query, limit)
        return await self._process_batch(raw_docs, knowledge_pack_id, document_type, knowledge_type) # type: ignore
    
    