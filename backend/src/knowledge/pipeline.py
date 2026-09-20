import hashlib

from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument
from src.knowledge.ingestion.extraction.registry import ExtractorRegistry
from src.knowledge.ingestion.extraction.chunking import Chuncking
from src.knowledge.ingestion.preprocessing.language import LanguageDetect
from src.knowledge.ingestion.preprocessing.metadata import TagExtractor
from src.knowledge.ingestion.preprocessing.quality import QualityScorer
from src.knowledge.ingestion.extraction.html_extractor import HTMLExtractor  # noqa: F401
from src.knowledge.ingestion.extraction.pdf_extractor import PdfExtractor  # noqa: F401
from src.knowledge.ingestion.extraction.text_extractor import TextExtractor  # noqa: F401
from src.knowledge.ingestion.validation.validator import Validator
from src.knowledge.ingestion.normalization.normalizer import Normalizer
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk
from src.knowledge.documents_schema.embeddend_chunk import EmbeddedChunk
from src.knowledge.documents_schema.chunk_payload import ChunkPayload
from src.rag.embeddings.bge_m3 import Embedding, EmbeddingResult
from src.rag.storage.base_vector_store import VectorPoint, DenseVector, SparseVector
from src.rag.storage.vector_store import QdrantVectorSearch
from src.repositories.document_repo import DocumentRepository
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
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
        pack_repo: KnowledgePackRepository
    ):
        self.chunker = Chuncking()
        self.normalizer = Normalizer()
        self.validator = Validator()
        self.embedder = Embedding()
        self.language_detector = LanguageDetect()
        self.tag_extractor = TagExtractor()
        self.quality_scorer = QualityScorer(normalizer=self.normalizer)
        self.vector_store = vector_store
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.pack_repo = pack_repo
    
    def _get_extractor(self, content_type: str):
        return ExtractorRegistry.create(content_type)
    
    def _extract(self, raw_doc: RawDocument) -> ExtractedDocument:
        
        extractor = self._get_extractor(raw_doc.content_type)
        return extractor.extract(raw_doc)
    
    def _language(self, extracted: ExtractedDocument) -> str:
        return self.language_detector.detect(extracted.text)
    
    def _chunk_and_filter(self, extracted: ExtractedDocument, language: str) -> list[KnowledgeChunk]:
        chunks = self.chunker.chunk(extracted)
        
        boilerplate_lines = self.normalizer.find_boilerplate(chunks)
        chunks = self.normalizer.normalize(chunks, boilerplate_lines)

        filtered_chunks = []

        for chunk in chunks:
            if not self.validator.validate(chunk):
                continue
            
            tags = self.tag_extractor.extract_tags(chunk.text, language, top_n = 10)
            quality = self.quality_scorer.score(chunk, boilerplate_lines)
            decision = self.quality_scorer.gate(quality)

            if decision == "reject":
                continue

            chunk.metadata["language"] = language
            chunk.metadata["quality_score"] = quality
            chunk.metadata["ingestion_priority"] = decision
            chunk.metadata["tags"] = tags
            
            filtered_chunks.append(chunk)

        return filtered_chunks
    
    async def _save_document(
        self,
        raw_doc: RawDocument,
        document_type: DocumentType,
        knowledge_type: KnowledgeType,
        knowledge_pack_id: int
    ) -> Document:
        
        doc_create = DocumentCreate(
            source = raw_doc.source,
            content_hash = raw_doc.content_hash,
            size = len(raw_doc.content),
            scraped_at = raw_doc.fetched_at,
            document_type = document_type,
            knowledge_type = knowledge_type,
            embedding_model = "BAAI/bge-m3",
            knowledge_pack_id = knowledge_pack_id
        )
        return await self.document_repo.create(**doc_create.model_dump())
    
    def _embed(self, chunks: list[KnowledgeChunk]) -> list[EmbeddedChunk]:
        if not chunks:
            return []
        result = []
        embedding_results = self.embedder.embed([chunk.text for chunk in chunks])
        
        for chunk, embedding_result in zip(chunks, embedding_results):
            result.append(EmbeddedChunk(
                        chunk = chunk,
                        dense_vector=embedding_result.dense.values,
                        sparse_indices=embedding_result.sparse.indices,
                        sparse_values=embedding_result.sparse.values
                        ))
            
        return result
            
    
    def _build_vector_points(
        self,
        embedded_chunks: list[EmbeddedChunk],
        document_id: int,
        document_type: DocumentType,
        pack_slug: str,
        domain_slug: str
    ) -> list[VectorPoint]:
        
        points = []
        for embedded_chunk in embedded_chunks:
            chunk = embedded_chunk.chunk
            point_id = hashlib.md5(f"{document_id}:{chunk.chunk_index}:{chunk.text}".encode()).hexdigest()
            points.append(VectorPoint(
                id=point_id,
                dense=DenseVector(values=embedded_chunk.dense_vector),
                sparse=SparseVector(
                    indices=embedded_chunk.sparse_indices,
                    values=embedded_chunk.sparse_values,
                ),
                payload = ChunkPayload(
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    knowledge_pack=pack_slug,
                    domain=domain_slug,
                    language=chunk.metadata['language'],
                    framework="unknown",
                    version = "unknown",
                    source_type = document_type.value,
                    tags = chunk.metadata['tags'],
                    quality_score=chunk.metadata['quality_score'],
                    title = "unknown"
               ).model_dump(),
            ))
            
        return points
    
    async def _save_chunk(
        self,
        embedded_chunks: list[EmbeddedChunk],
        points: list[VectorPoint],
        document_id: int
    ) -> None:
        
        await self.chunk_repo.bulk_create([
            {
                "document_id": document_id,
                "chunk_index": embedded_chunk.chunk.chunk_index,
                "qdrant_point_id": point.id,
                "token_count": embedded_chunk.chunk.token_count
            }
            for embedded_chunk, point in zip(embedded_chunks, points)
        ])
        
    async def process(
        self,
        raw_doc: RawDocument,
        document_type: DocumentType,
        knowledge_type: KnowledgeType,
        knowledge_pack_id: int
    ) -> Document:

        pack = await self.pack_repo.get_by_id(knowledge_pack_id)
        if pack is None:
            raise ValueError(f'Pack with id={knowledge_pack_id} does not exist')
        
        extracted = self._extract(raw_doc)
        language = self._language(extracted)
        chunks = self._chunk_and_filter(extracted, language)

        if not chunks:
            raise ValueError(f"No valid chunks extracted from {raw_doc.source}")
        document = await self._save_document(raw_doc, document_type, knowledge_type, knowledge_pack_id)
        
        try:
            embedded_chunks = self._embed(chunks)
            points = self._build_vector_points(embedded_chunks, document.id, document_type, pack.slug, pack.domain.slug)
            upserted = False
            try:
                await self.vector_store.upsert_batch(points)
                upserted = True
                await self._save_chunk(embedded_chunks, points, document.id)
                await self.document_repo.update_status(document.id, DocumentStatus.INDEXED)
            except Exception:
                if upserted:
                    for point in points:
                        await self.vector_store.delete(point.id)
                raise
        except Exception as e:
            await self.document_repo.update_status(document.id, DocumentStatus.FAILED)
            raise e

        return document
        