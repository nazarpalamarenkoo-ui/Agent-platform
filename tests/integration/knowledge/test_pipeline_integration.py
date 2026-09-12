import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge.pipeline import IngestionPipeline
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk
from src.knowledge.documents_schema.embeddend_chunk import EmbeddedChunk
from src.rag.storage.base_vector_store import DenseVector, SparseVector
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.db.enums.document_status import DocumentStatus
from src.db.models.document import Document

pytestmark = pytest.mark.integration

def make_raw_doc(content_type: str = "text/plain") -> RawDocument:
    content = b"Some raw content to be ingested."
    return RawDocument(
        source="https://example.com/doc.txt",
        content=content,
        content_type=content_type,
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )


def make_chunks(n: int = 2) -> list[KnowledgeChunk]:
    return [
        KnowledgeChunk(
            chunk_index=i,
            text=f"chunk text {i}",
            token_count=10,
            metadata={
                "source": "https://example.com/doc.txt",
                "page": 1,
                "language": "en",
                "quality_score": 0.9,
                "ingestion_priority": "high",
                "tags": ["tag1"],
            },
        )
        for i in range(n)
    ]


def make_embedded_chunks(chunks: list[KnowledgeChunk]) -> list[EmbeddedChunk]:
    return [
        EmbeddedChunk(
            chunk=chunk,
            dense_vector=[0.1, 0.2, 0.3],
            sparse_indices=[0, 5],
            sparse_values=[0.5, 0.2],
        )
        for chunk in chunks
    ]


def make_pack(slug: str = "my-pack", domain_slug: str = "engineering"):
    pack = MagicMock()
    pack.slug = slug
    pack.domain = MagicMock()
    pack.domain.slug = domain_slug
    return pack


@pytest.fixture
def vector_store():
    store = MagicMock()
    store.upsert_batch = AsyncMock()
    store.delete = AsyncMock()
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
def pack_repo():
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=make_pack())
    return repo


@pytest.fixture
def pipeline(vector_store, document_repo, chunk_repo, pack_repo):
    """
    Fully mocked pipeline. Internal collaborators are replaced so tests stay
    fast and deterministic.
    """
    chunks = make_chunks(2)
    embedded = make_embedded_chunks(chunks)

    with patch("src.knowledge.pipeline.Chuncking"), \
         patch("src.knowledge.pipeline.Normalizer"), \
         patch("src.knowledge.pipeline.Validator"), \
         patch("src.knowledge.pipeline.Embedding"), \
         patch("src.knowledge.pipeline.LanguageDetect"), \
         patch("src.knowledge.pipeline.TagExtractor"), \
         patch("src.knowledge.pipeline.QualityScorer"), \
         patch("src.knowledge.pipeline.ExtractorRegistry"):

        p = IngestionPipeline(
            vector_store=vector_store,
            document_repo=document_repo,
            chunk_repo=chunk_repo,
            pack_repo=pack_repo,
        )

    # Override pipeline internals with controlled mocks
    extracted_doc = MagicMock()
    extracted_doc.text = "EXTRACTED"

    p._extract = MagicMock(return_value=extracted_doc)
    p._language = MagicMock(return_value="en")
    p._chunk_and_filter = MagicMock(return_value=chunks)
    p._embed = MagicMock(return_value=embedded)
    p._build_vector_points = MagicMock(
        return_value=[
            MagicMock(
                id=hashlib.md5(f"42:{i}:chunk text {i}".encode()).hexdigest(),
                payload={"document_id": 42},
            )
            for i in range(2)
        ]
    )

    return p


class TestIngestionPipelineHappyPath:

    @pytest.mark.asyncio
    async def test_process_runs_full_pipeline_and_returns_document(
        self, pipeline, document_repo, vector_store, chunk_repo, pack_repo
    ):
        raw_doc = make_raw_doc()
        saved_document = Document(id=42, status=DocumentStatus.PENDING)
        document_repo.create.return_value = saved_document

        result = await pipeline.process(
            raw_doc, DocumentType.BLOG_POST, KnowledgeType.REFERENCE, knowledge_pack_id=1
        )

        assert result is saved_document

        # pack looked up first
        pack_repo.get_by_id.assert_awaited_once_with(1)

        # extraction → language → chunk-and-filter happened
        pipeline._extract.assert_called_once_with(raw_doc)
        pipeline._language.assert_called_once()
        pipeline._chunk_and_filter.assert_called_once()

        # document persisted before embedding/indexing
        document_repo.create.assert_awaited_once()

        # embedding + vector store upsert happened
        pipeline._embed.assert_called_once()
        vector_store.upsert_batch.assert_awaited_once()

        # chunk metadata persisted
        chunk_repo.bulk_create.assert_awaited_once()
        saved_rows = chunk_repo.bulk_create.await_args.args[0]
        assert len(saved_rows) == 2
        assert {row["document_id"] for row in saved_rows} == {42}

        # final status flipped to INDEXED, never to FAILED
        document_repo.update_status.assert_awaited_once_with(42, DocumentStatus.INDEXED)
        # no rollback delete calls
        vector_store.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_vector_point_ids_are_deterministic_per_document_and_chunk(
        self, pipeline, document_repo, vector_store
    ):
        """Point IDs must be stable md5(document_id:chunk_index:text)."""
        saved_document = Document(id=99, status=DocumentStatus.PENDING)
        document_repo.create.return_value = saved_document

        # Let _build_vector_points run the real logic for this test
        pipeline._build_vector_points = IngestionPipeline._build_vector_points.__get__(
            pipeline, IngestionPipeline
        )

        chunks = make_chunks(2)
        pipeline._chunk_and_filter.return_value = chunks
        pipeline._embed.return_value = make_embedded_chunks(chunks)

        await pipeline.process(
            make_raw_doc(), DocumentType.PAPER, KnowledgeType.PRINCIPLE, knowledge_pack_id=1
        )

        points = vector_store.upsert_batch.await_args.args[0]
        expected_id_0 = hashlib.md5(f"99:0:chunk text 0".encode()).hexdigest()
        assert points[0].id == expected_id_0


# ---------------------------------------------------------------------------
# Failure-path tests
# ---------------------------------------------------------------------------

class TestIngestionPipelineFailurePaths:

    @pytest.mark.asyncio
    async def test_unknown_pack_raises_before_extracting(
        self, pipeline, document_repo, pack_repo
    ):
        pack_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Pack with id=99 does not exist"):
            await pipeline.process(
                make_raw_doc(), DocumentType.BLOG_POST, KnowledgeType.REFERENCE,
                knowledge_pack_id=99
            )

        # Nothing should have been persisted
        document_repo.create.assert_not_awaited()
        document_repo.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_extraction_failure_propagates_and_skips_persistence(
        self, pipeline, document_repo
    ):
        pipeline._extract.side_effect = ValueError("corrupt file")

        with pytest.raises(ValueError, match="corrupt file"):
            await pipeline.process(
                make_raw_doc(), DocumentType.PAPER, KnowledgeType.REFERENCE,
                knowledge_pack_id=1
            )

        document_repo.create.assert_not_awaited()
        document_repo.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_chunks_raises_before_saving_document(
        self, pipeline, document_repo
    ):
        """If all chunks are filtered out, process() raises before DB write."""
        pipeline._chunk_and_filter.return_value = []

        with pytest.raises(ValueError, match="No valid chunks extracted"):
            await pipeline.process(
                make_raw_doc(), DocumentType.MANUAL, KnowledgeType.EXAMPLE,
                knowledge_pack_id=1
            )

        document_repo.create.assert_not_awaited()
        document_repo.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_vector_store_failure_marks_document_failed_and_reraises(
        self, pipeline, document_repo, vector_store
    ):
        document_repo.create.return_value = Document(id=5, status=DocumentStatus.PENDING)
        vector_store.upsert_batch.side_effect = RuntimeError("qdrant unreachable")

        with pytest.raises(RuntimeError, match="qdrant unreachable"):
            await pipeline.process(
                make_raw_doc(), DocumentType.ARCHITECTURE_DOC, KnowledgeType.PRINCIPLE,
                knowledge_pack_id=1
            )

        document_repo.update_status.assert_awaited_once_with(5, DocumentStatus.FAILED)
        # upsert never completed → no rollback deletes expected
        vector_store.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chunk_repo_failure_marks_document_failed_and_rolls_back_vectors(
        self, pipeline, document_repo, chunk_repo, vector_store
    ):
        """
        If bulk_create fails after a successful upsert_batch, the pipeline must
        delete the already-upserted vector points (rollback) and mark FAILED.
        """
        document_repo.create.return_value = Document(id=6, status=DocumentStatus.PENDING)
        chunk_repo.bulk_create.side_effect = RuntimeError("db write failed")

        with pytest.raises(RuntimeError, match="db write failed"):
            await pipeline.process(
                make_raw_doc(), DocumentType.BOOK, KnowledgeType.EXAMPLE,
                knowledge_pack_id=1
            )

        document_repo.update_status.assert_awaited_once_with(6, DocumentStatus.FAILED)
        # vector rollback: delete called once per point
        assert vector_store.delete.await_count == len(pipeline._build_vector_points.return_value)

    @pytest.mark.asyncio
    async def test_embedder_failure_marks_document_failed(
        self, pipeline, document_repo
    ):
        document_repo.create.return_value = Document(id=8, status=DocumentStatus.PENDING)
        pipeline._embed.side_effect = RuntimeError("embedding service down")

        with pytest.raises(RuntimeError, match="embedding service down"):
            await pipeline.process(
                make_raw_doc(), DocumentType.PAPER, KnowledgeType.REFERENCE,
                knowledge_pack_id=1
            )

        document_repo.update_status.assert_awaited_once_with(8, DocumentStatus.FAILED)