import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.knowledge.pipeline import IngestionPipeline
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk
from src.rag.embeddings.bge_m3 import EmbeddingResult
from src.rag.storage.base_vector_store import DenseVector, SparseVector
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.db.enums.document_status import DocumentStatus
from src.db.models.document import Document


def make_raw_doc(content_type: str = "text/plain") -> RawDocument:
    content = b"Some raw content to be ingested."
    return RawDocument(
        source="https://example.com/doc.txt",
        content=content,
        content_type=content_type,
        content_hash=hashlib.sha256(content).hexdigest(),  # sha256 -> 64 hex chars
        fetched_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )


def make_chunks(n: int = 2) -> list[KnowledgeChunk]:
    return [
        KnowledgeChunk(
            chunk_index=i,
            text=f"chunk text {i}",
            token_count=10,
            metadata={"source": "https://example.com/doc.txt", "page": 1},
        )
        for i in range(n)
    ]


def make_embeddings(n: int = 2) -> list[EmbeddingResult]:
    return [
        EmbeddingResult(
            dense=DenseVector(values=[0.1, 0.2, 0.3]),
            sparse=SparseVector(indices=[0, 5], values=[0.5, 0.2]),
        )
        for _ in range(n)
    ]


@pytest.fixture
def _patch_embedding_model(monkeypatch):
    monkeypatch.setattr(
        "src.rag.embeddings.bge_m3.BGEM3FlagModel",
        lambda *args, **kwargs: MagicMock(),
    )


@pytest.fixture
def vector_store():
    store = MagicMock()
    store.upsert_batch = AsyncMock()
    return store


@pytest.fixture
def document_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.update_status = AsyncMock()
    return repo


@pytest.fixture
def chunk_repo():
    repo = MagicMock()
    repo.bulk_create = AsyncMock()
    return repo


@pytest.fixture
def pipeline(vector_store, document_repo, chunk_repo, _patch_embedding_model):
    pipeline = IngestionPipeline(
        vector_store=vector_store,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
    )
    pipeline.extractors = {
        "text/plain": MagicMock(extract=MagicMock(return_value="EXTRACTED")),
    }
    pipeline.chunker = MagicMock(chunk=MagicMock(return_value=make_chunks(2)))
    pipeline.normalizer = MagicMock(normalize=MagicMock(side_effect=lambda chunks: chunks))
    pipeline.validator = MagicMock(validate=MagicMock(return_value=True))
    pipeline.embedder = MagicMock(embed=MagicMock(return_value=make_embeddings(2)))
    return pipeline


class TestIngestionPipelineHappyPath:

    @pytest.mark.asyncio
    async def test_process_runs_full_pipeline_and_returns_document(
        self, pipeline, document_repo, vector_store, chunk_repo
    ):
        raw_doc = make_raw_doc()
        saved_document = Document(id=42, status=DocumentStatus.PENDING)
        document_repo.create.return_value = saved_document

        result = await pipeline.process(
            raw_doc, DocumentType.BLOG_POST, KnowledgeType.REFERENCE
        )

        assert result is saved_document

        # extraction -> chunking -> normalization -> validation happened
        pipeline.extractors["text/plain"].extract.assert_called_once_with(raw_doc)
        pipeline.chunker.chunk.assert_called_once_with("EXTRACTED")
        pipeline.normalizer.normalize.assert_called_once()
        assert pipeline.validator.validate.call_count == 2  # one per chunk

        # document persisted before embedding/indexing
        document_repo.create.assert_awaited_once()

        # embedding + vector store upsert happened with 2 chunks
        pipeline.embedder.embed.assert_called_once()
        vector_store.upsert_batch.assert_awaited_once()
        upserted_points = vector_store.upsert_batch.await_args.args[0]
        assert len(upserted_points) == 2
        assert all(p.payload["document_id"] == 42 for p in upserted_points)

        # chunk metadata persisted
        chunk_repo.bulk_create.assert_awaited_once()
        saved_rows = chunk_repo.bulk_create.await_args.args[0]
        assert len(saved_rows) == 2
        assert {row["document_id"] for row in saved_rows} == {42}

        # final status flipped to INDEXED, never to FAILED
        document_repo.update_status.assert_awaited_once_with(42, DocumentStatus.INDEXED)

    @pytest.mark.asyncio
    async def test_process_with_zero_valid_chunks_still_indexes_document(
        self, pipeline, document_repo, vector_store, chunk_repo
    ):
        # All chunks get filtered out by the validator
        pipeline.validator.validate = MagicMock(return_value=False)
        document_repo.create.return_value = Document(id=7, status=DocumentStatus.PENDING)

        result = await pipeline.process(
            make_raw_doc(), DocumentType.MANUAL, KnowledgeType.EXAMPLE
        )

        assert result.id == 7
        # short-circuit: _embed() returns [] early and never calls the
        # (expensive) embedder when there are no chunks to embed
        pipeline.embedder.embed.assert_not_called()
        vector_store.upsert_batch.assert_awaited_once_with([])
        chunk_repo.bulk_create.assert_awaited_once_with([])
        document_repo.update_status.assert_awaited_once_with(7, DocumentStatus.INDEXED)

    @pytest.mark.asyncio
    async def test_vector_point_ids_are_deterministic_per_document_and_chunk(
        self, pipeline, document_repo, vector_store
    ):
        document_repo.create.return_value = Document(id=99, status=DocumentStatus.PENDING)

        await pipeline.process(make_raw_doc(), DocumentType.PAPER, KnowledgeType.PRINCIPLE)

        points = vector_store.upsert_batch.await_args.args[0]
        expected_id_0 = hashlib.md5(f"99:0:chunk text 0".encode()).hexdigest()
        assert points[0].id == expected_id_0

class TestIngestionPipelineFailurePaths:

    @pytest.mark.asyncio
    async def test_unsupported_content_type_raises_before_saving_document(
        self, pipeline, document_repo
    ):
        raw_doc = make_raw_doc(content_type="application/zip")

        with pytest.raises(ValueError, match="No extractor for content_type"):
            await pipeline.process(raw_doc, DocumentType.PDF, KnowledgeType.REFERENCE)

        document_repo.create.assert_not_awaited()
        document_repo.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_extraction_failure_propagates_and_skips_persistence(
        self, pipeline, document_repo
    ):
        pipeline.extractors["text/plain"].extract.side_effect = ValueError("corrupt file")

        with pytest.raises(ValueError, match="corrupt file"):
            await pipeline.process(make_raw_doc(), DocumentType.PDF, KnowledgeType.REFERENCE)

        document_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_vector_store_failure_marks_document_failed_and_reraises(
        self, pipeline, document_repo, vector_store
    ):
        document_repo.create.return_value = Document(id=5, status=DocumentStatus.PENDING)
        vector_store.upsert_batch.side_effect = RuntimeError("qdrant unreachable")

        with pytest.raises(RuntimeError, match="qdrant unreachable"):
            await pipeline.process(make_raw_doc(), DocumentType.ARCHITECTURE_DOC, KnowledgeType.PRINCIPLE)

        document_repo.update_status.assert_awaited_once_with(5, DocumentStatus.FAILED)

    @pytest.mark.asyncio
    async def test_chunk_repo_failure_marks_document_failed(
        self, pipeline, document_repo, chunk_repo
    ):
        document_repo.create.return_value = Document(id=6, status=DocumentStatus.PENDING)
        chunk_repo.bulk_create.side_effect = RuntimeError("db write failed")

        with pytest.raises(RuntimeError, match="db write failed"):
            await pipeline.process(make_raw_doc(), DocumentType.BOOK, KnowledgeType.EXAMPLE)

        document_repo.update_status.assert_awaited_once_with(6, DocumentStatus.FAILED)

    @pytest.mark.asyncio
    async def test_embedder_failure_marks_document_failed(
        self, pipeline, document_repo
    ):
        document_repo.create.return_value = Document(id=8, status=DocumentStatus.PENDING)
        pipeline.embedder.embed.side_effect = RuntimeError("embedding service down")

        with pytest.raises(RuntimeError, match="embedding service down"):
            await pipeline.process(make_raw_doc(), DocumentType.PAPER, KnowledgeType.REFERENCE)

        document_repo.update_status.assert_awaited_once_with(8, DocumentStatus.FAILED)