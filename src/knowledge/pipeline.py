import hashlib
from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument
from src.knowledge.ingestion.extraction.pdf_extractor import PdfExtractor
from src.knowledge.ingestion.extraction.text_extractor import TextExtractor
from src.knowledge.ingestion.extraction.html_extractor import HTMLExtractor
from src.knowledge.ingestion.extraction.chunking import Chuncking
from src.knowledge.ingestion.validation.validator import Validator
from src.knowledge.ingestion.normalization.normalizer import Normalizer
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk
from src.rag.embeddings.bge_m3 import Embedding, EmbeddingResult
from src.rag.storage.base_vector_store import VectorPoint
from src.rag.storage.vector_store import QdrantVectorSearch
from src.repositories.document_repo import DocumentRepository
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.schemas.document import DocumentCreate
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.db.enums.document_status import DocumentStatus
from src.db.models.document import Document

class IngestionPipeline:
    
    def __init__(
        self,
        vector_store: QdrantVectorSearch,
        document_repo: DocumentRepository,
        chunk_repo: DocumentChunkRepository,
    ):
        self.extractors = {
            "application/pdf": PdfExtractor(),
            "text/plain": TextExtractor(),
            'text/html': HTMLExtractor(),
        }
        self.chunker = Chuncking()
        self.normalizer = Normalizer()
        self.validator = Validator()
        self.embedder = Embedding()
        self.vector_store = vector_store
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
    
    def _get_extractor(self, content_type: str):
        
        extractor = self.extractors.get(content_type)
        if extractor is None:
            raise ValueError(f"No extractor for content_type: {content_type}")
        return extractor
    
    def _extract(self, raw_doc: RawDocument) -> ExtractedDocument:
        
        extractor = self._get_extractor(raw_doc.content_type)
        return extractor.extract(raw_doc)
    
    def _chunk_and_filter(self, extracted: ExtractedDocument) -> list[KnowledgeChunk]:
        chunks = self.chunker.chunk(extracted)
        chunks = self.normalizer.normalize(chunks)
        return [chunk for chunk in chunks if self.validator.validate(chunk)]
    
    async def _save_document(
        self,
        raw_doc: RawDocument,
        document_type: DocumentType,
        knowledge_type: KnowledgeType
    ) -> Document:
        
        doc_create = DocumentCreate(
            source = raw_doc.source,
            content_hash = raw_doc.content_hash,
            size = len(raw_doc.content),
            scraped_at = raw_doc.fetched_at,
            document_type = document_type,
            knowledge_type = knowledge_type,
            embedding_model = "BAAI/bge-m3"
        )
        return await self.document_repo.create(**doc_create.model_dump())
    
    def _embed(self, chunks: list[KnowledgeChunk]) -> list[EmbeddingResult]:
        if not chunks:
            return []

        return self.embedder.embed([chunk.text for chunk in chunks])
    
    def _build_vector_points(
        self,
        chunks: list[KnowledgeChunk],
        embeddings: list[EmbeddingResult],
        document_id: int
    ) -> list[VectorPoint]:
        
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            point_id = hashlib.md5(f"{document_id}:{chunk.chunk_index}:{chunk.text}".encode()).hexdigest()
            points.append(VectorPoint(
                id = point_id,
                dense = embedding.dense,
                sparse = embedding.sparse,
                payload = {
                    "document_id": document_id,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "source": chunk.metadata.get("source"),
                    "page": chunk.metadata.get("page")
                },
            ))
            
        return points
    
    async def _save_chunk(
        self,
        chunks: list[KnowledgeChunk],
        points: list[VectorPoint],
        document_id: int
    ) -> None:
        
        await self.chunk_repo.bulk_create([
            {
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "qdrant_point_id": point.id,
                "token_count": chunk.token_count
            }
            for chunk, point in zip(chunks, points)
        ])
        
    async def process(
        self,
        raw_doc: RawDocument,
        document_type: DocumentType,
        knowledge_type: KnowledgeType,
    ) -> Document:

        try:
            extracted = self._extract(raw_doc)
            chunks = self._chunk_and_filter(extracted)
        except ValueError:
            raise

        document = await self._save_document(raw_doc, document_type, knowledge_type)

        try:
            embeddings = self._embed(chunks)
            points = self._build_vector_points(chunks, embeddings, document.id)
            await self.vector_store.upsert_batch(points)
            await self._save_chunk(chunks, points, document.id)
            await self.document_repo.update_status(document.id, DocumentStatus.INDEXED)
        except Exception as e:
            await self.document_repo.update_status(document.id, DocumentStatus.FAILED)
            raise e

        return document
        