import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge.pipeline import IngestionPipeline
from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk
from src.rag.embeddings.bge_m3 import EmbeddingResult
from src.rag.storage.base_vector_store import VectorPoint
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.db.enums.document_status import DocumentStatus
from src.db.models.document import Document


def make_raw_document(content_type="text/plain", content=b"hello world", source="https://example.com"):
    return RawDocument(
        source=source,
        content=content,
        content_type=content_type,
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at=datetime.now(timezone.utc),
    )


def make_chunk(text="chunk text", index=0, token_count=2, metadata=None):
    return KnowledgeChunk(chunk_index=index, text=text, token_count=token_count, metadata=metadata or {})


@pytest.fixture
def mock_deps():
    vector_store = MagicMock()
    vector_store.upsert_batch = AsyncMock()

    document_repo = MagicMock()
    document_repo.create = AsyncMock()
    document_repo.update_status = AsyncMock()

    chunk_repo = MagicMock()
    chunk_repo.bulk_create = AsyncMock()

    return vector_store, document_repo, chunk_repo


@pytest.fixture
def pipeline(mock_deps):
    vector_store, document_repo, chunk_repo = mock_deps

    # Chuncking() calls tiktoken.get_encoding('cl100k_base') at construction
    # time, which needs network access this sandbox doesn't have. The real
    # encoder is never used in these tests since self.chunker is replaced
    # with a mock right after construction, so a stub is enough here.
    with patch(
        "src.knowledge.ingestion.extraction.chunking.tiktoken.get_encoding",
        return_value=MagicMock(),
    ):
        instance = IngestionPipeline(
            vector_store=vector_store, document_repo=document_repo, chunk_repo=chunk_repo
        )

    # Replace the internally-constructed collaborators with mocks so each
    # test can drive `process()`'s orchestration logic in isolation.
    instance.chunker = MagicMock()
    instance.normalizer = MagicMock()
    instance.validator = MagicMock()
    instance.embedder = MagicMock()
    instance.extractors = {
        "text/plain": MagicMock(),
        "text/html": MagicMock(),
        "application/pdf": MagicMock(),
    }

    return instance


class TestGetExtractor:

    def test_returns_extractor_for_known_content_type(self, pipeline):
        extractor = pipeline._get_extractor("text/plain")
        assert extractor is pipeline.extractors["text/plain"]

    def test_raises_value_error_for_unknown_content_type(self, pipeline):
        with pytest.raises(ValueError, match="No extractor for content_type"):
            pipeline._get_extractor("application/unknown")


class TestExtract:

    def test_delegates_to_extractor_for_raw_docs_content_type(self, pipeline):
        raw_doc = make_raw_document(content_type="text/plain")
        expected = ExtractedDocument(text="extracted", metadata={"source": raw_doc.source})
        pipeline.extractors["text/plain"].extract.return_value = expected

        result = pipeline._extract(raw_doc)

        assert result is expected
        pipeline.extractors["text/plain"].extract.assert_called_once_with(raw_doc)


class TestChunkAndFilter:

    def test_chains_chunker_normalizer_and_validator(self, pipeline):
        extracted = ExtractedDocument(text="text", metadata={})
        chunk_a, chunk_b, chunk_c = make_chunk("a", 0), make_chunk("b", 1), make_chunk("c", 2)

        pipeline.chunker.chunk.return_value = [chunk_a, chunk_b, chunk_c]
        pipeline.normalizer.normalize.return_value = [chunk_a, chunk_b]
        pipeline.validator.validate.side_effect = [True, False]

        result = pipeline._chunk_and_filter(extracted)

        pipeline.chunker.chunk.assert_called_once_with(extracted)
        pipeline.normalizer.normalize.assert_called_once_with([chunk_a, chunk_b, chunk_c])
        assert result == [chunk_a]

    def test_returns_empty_list_when_all_chunks_filtered_out(self, pipeline):
        extracted = ExtractedDocument(text="text", metadata={})
        pipeline.chunker.chunk.return_value = [make_chunk("a", 0)]
        pipeline.normalizer.normalize.return_value = [make_chunk("a", 0)]
        pipeline.validator.validate.return_value = False

        result = pipeline._chunk_and_filter(extracted)

        assert result == []


class TestSaveDocument:

    @pytest.mark.asyncio
    async def test_builds_expected_document_create_payload(self, pipeline, mock_deps):
        _, document_repo, _ = mock_deps
        raw_doc = make_raw_document(content=b"some file content")
        document_repo.create.return_value = Document(id=1)

        await pipeline._save_document(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE)

        document_repo.create.assert_awaited_once()
        _, kwargs = document_repo.create.call_args
        assert kwargs["source"] == raw_doc.source
        assert kwargs["content_hash"] == raw_doc.content_hash
        assert kwargs["size"] == len(raw_doc.content)
        assert kwargs["scraped_at"] == raw_doc.fetched_at
        assert kwargs["document_type"] == DocumentType.BOOK
        assert kwargs["knowledge_type"] == KnowledgeType.REFERENCE
        assert kwargs["embedding_model"] == "BAAI/bge-m3"

    @pytest.mark.asyncio
    async def test_returns_repo_created_document(self, pipeline, mock_deps):
        _, document_repo, _ = mock_deps
        raw_doc = make_raw_document()
        created = Document(id=99)
        document_repo.create.return_value = created

        result = await pipeline._save_document(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE)

        assert result is created


class TestEmbed:

    def test_returns_empty_list_without_calling_embedder_for_no_chunks(self, pipeline):
        result = pipeline._embed([])

        assert result == []
        pipeline.embedder.embed.assert_not_called()

    def test_calls_embedder_with_chunk_texts_in_order(self, pipeline):
        chunks = [make_chunk("first", 0), make_chunk("second", 1)]
        expected = [EmbeddingResult(dense=[0.1], sparse={}), EmbeddingResult(dense=[0.2], sparse={})]
        pipeline.embedder.embed.return_value = expected

        result = pipeline._embed(chunks)

        pipeline.embedder.embed.assert_called_once_with(["first", "second"])
        assert result == expected


class TestBuildVectorPoints:

    def test_builds_one_point_per_chunk_with_expected_payload(self, pipeline):
        chunk = make_chunk("hello", index=0, metadata={"source": "doc.txt", "page": 3})
        embedding = EmbeddingResult(dense=[0.1, 0.2], sparse={1: 0.5})

        points = pipeline._build_vector_points([chunk], [embedding], document_id=42)

        assert len(points) == 1
        point = points[0]
        assert isinstance(point, VectorPoint)
        expected_id = hashlib.md5(f"42:0:hello".encode()).hexdigest()
        assert point.id == expected_id
        assert point.dense == [0.1, 0.2]
        assert point.sparse == {1: 0.5}
        assert point.payload == {
            "document_id": 42,
            "chunk_index": 0,
            "text": "hello",
            "source": "doc.txt",
            "page": 3,
        }

    def test_missing_metadata_fields_default_to_none_in_payload(self, pipeline):
        chunk = make_chunk("no metadata", index=0, metadata={})
        embedding = EmbeddingResult(dense=[], sparse={})

        points = pipeline._build_vector_points([chunk], [embedding], document_id=1)

        assert points[0].payload["source"] is None
        assert points[0].payload["page"] is None

    def test_stops_at_shorter_of_chunks_or_embeddings(self, pipeline):
        chunks = [make_chunk("a", 0), make_chunk("b", 1)]
        embeddings = [EmbeddingResult(dense=[0.1], sparse={})]

        points = pipeline._build_vector_points(chunks, embeddings, document_id=1)

        assert len(points) == 1

    def test_point_ids_are_deterministic_for_same_inputs(self, pipeline):
        chunk = make_chunk("stable text", index=2)
        embedding = EmbeddingResult(dense=[0.1], sparse={})

        first = pipeline._build_vector_points([chunk], [embedding], document_id=5)
        second = pipeline._build_vector_points([chunk], [embedding], document_id=5)

        assert first[0].id == second[0].id


class TestSaveChunk:

    @pytest.mark.asyncio
    async def test_bulk_creates_rows_matching_chunks_and_points(self, pipeline, mock_deps):
        _, _, chunk_repo = mock_deps
        chunk = make_chunk("text", index=0, token_count=7)
        point = VectorPoint(id="point-id-1", dense=[0.1], sparse={}, payload={})

        await pipeline._save_chunk([chunk], [point], document_id=3)

        chunk_repo.bulk_create.assert_awaited_once_with([
            {
                "document_id": 3,
                "chunk_index": 0,
                "qdrant_point_id": "point-id-1",
                "token_count": 7,
            }
        ])

    @pytest.mark.asyncio
    async def test_empty_inputs_calls_bulk_create_with_empty_list(self, pipeline, mock_deps):
        _, _, chunk_repo = mock_deps

        await pipeline._save_chunk([], [], document_id=3)

        chunk_repo.bulk_create.assert_awaited_once_with([])


class TestProcess:

    @pytest.mark.asyncio
    async def test_success_path_returns_document_and_marks_indexed(self, pipeline, mock_deps):
        vector_store, document_repo, chunk_repo = mock_deps
        raw_doc = make_raw_document(content_type="text/plain")

        extracted = ExtractedDocument(text="some text", metadata={"source": raw_doc.source})
        pipeline.extractors["text/plain"].extract.return_value = extracted

        chunk = make_chunk("chunk text", index=0)
        pipeline.chunker.chunk.return_value = [chunk]
        pipeline.normalizer.normalize.return_value = [chunk]
        pipeline.validator.validate.return_value = True

        pipeline.embedder.embed.return_value = [EmbeddingResult(dense=[0.1], sparse={})]

        document_repo.create.return_value = Document(id=10)

        result = await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE)

        assert result.id == 10
        vector_store.upsert_batch.assert_awaited_once()
        chunk_repo.bulk_create.assert_awaited_once()
        document_repo.update_status.assert_awaited_once_with(10, DocumentStatus.INDEXED)

    @pytest.mark.asyncio
    async def test_unknown_content_type_raises_before_saving_document(self, pipeline, mock_deps):
        _, document_repo, _ = mock_deps
        raw_doc = make_raw_document(content_type="application/unknown")

        with pytest.raises(ValueError):
            await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE)

        document_repo.create.assert_not_awaited()
        document_repo.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_embedding_failure_marks_document_failed_and_reraises(self, pipeline, mock_deps):
        vector_store, document_repo, chunk_repo = mock_deps
        raw_doc = make_raw_document(content_type="text/plain")

        extracted = ExtractedDocument(text="text", metadata={})
        pipeline.extractors["text/plain"].extract.return_value = extracted

        chunk = make_chunk("chunk", index=0)
        pipeline.chunker.chunk.return_value = [chunk]
        pipeline.normalizer.normalize.return_value = [chunk]
        pipeline.validator.validate.return_value = True

        pipeline.embedder.embed.side_effect = RuntimeError("embedding backend down")
        document_repo.create.return_value = Document(id=7)

        with pytest.raises(RuntimeError, match="embedding backend down"):
            await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE)

        document_repo.update_status.assert_awaited_once_with(7, DocumentStatus.FAILED)
        vector_store.upsert_batch.assert_not_awaited()
        chunk_repo.bulk_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_vector_store_failure_marks_document_failed_and_reraises(self, pipeline, mock_deps):
        vector_store, document_repo, chunk_repo = mock_deps
        raw_doc = make_raw_document(content_type="text/plain")

        pipeline.extractors["text/plain"].extract.return_value = ExtractedDocument(text="text", metadata={})
        chunk = make_chunk("chunk", index=0)
        pipeline.chunker.chunk.return_value = [chunk]
        pipeline.normalizer.normalize.return_value = [chunk]
        pipeline.validator.validate.return_value = True
        pipeline.embedder.embed.return_value = [EmbeddingResult(dense=[0.1], sparse={})]

        vector_store.upsert_batch.side_effect = ConnectionError("qdrant unreachable")
        document_repo.create.return_value = Document(id=8)

        with pytest.raises(ConnectionError, match="qdrant unreachable"):
            await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE)

        document_repo.update_status.assert_awaited_once_with(8, DocumentStatus.FAILED)
        chunk_repo.bulk_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chunk_repo_failure_marks_document_failed_and_reraises(self, pipeline, mock_deps):
        vector_store, document_repo, chunk_repo = mock_deps
        raw_doc = make_raw_document(content_type="text/plain")

        pipeline.extractors["text/plain"].extract.return_value = ExtractedDocument(text="text", metadata={})
        chunk = make_chunk("chunk", index=0)
        pipeline.chunker.chunk.return_value = [chunk]
        pipeline.normalizer.normalize.return_value = [chunk]
        pipeline.validator.validate.return_value = True
        pipeline.embedder.embed.return_value = [EmbeddingResult(dense=[0.1], sparse={})]

        chunk_repo.bulk_create.side_effect = RuntimeError("db write failed")
        document_repo.create.return_value = Document(id=9)

        with pytest.raises(RuntimeError, match="db write failed"):
            await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE)

        vector_store.upsert_batch.assert_awaited_once()
        document_repo.update_status.assert_awaited_once_with(9, DocumentStatus.FAILED)

    @pytest.mark.asyncio
    async def test_all_chunks_filtered_out_still_succeeds_with_empty_batches(self, pipeline, mock_deps):
        vector_store, document_repo, chunk_repo = mock_deps
        raw_doc = make_raw_document(content_type="text/plain")

        pipeline.extractors["text/plain"].extract.return_value = ExtractedDocument(text="text", metadata={})
        pipeline.chunker.chunk.return_value = [make_chunk("too short", 0)]
        pipeline.normalizer.normalize.return_value = []
        document_repo.create.return_value = Document(id=11)

        result = await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE)

        assert result.id == 11
        pipeline.embedder.embed.assert_not_called()
        vector_store.upsert_batch.assert_awaited_once_with([])
        chunk_repo.bulk_create.assert_awaited_once_with([])
        document_repo.update_status.assert_awaited_once_with(11, DocumentStatus.INDEXED)

    @pytest.mark.asyncio
    async def test_uses_extractor_matching_raw_docs_content_type(self, pipeline, mock_deps):
        _, document_repo, _ = mock_deps
        raw_doc = make_raw_document(content_type="application/pdf")

        pipeline.extractors["application/pdf"].extract.return_value = ExtractedDocument(text="pdf text", metadata={})
        pipeline.chunker.chunk.return_value = []
        pipeline.normalizer.normalize.return_value = []
        document_repo.create.return_value = Document(id=12)

        await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE)

        pipeline.extractors["application/pdf"].extract.assert_called_once_with(raw_doc)
        pipeline.extractors["text/plain"].extract.assert_not_called()
        pipeline.extractors["text/html"].extract.assert_not_called()