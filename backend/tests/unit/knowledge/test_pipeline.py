import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge.pipeline import IngestionPipeline
from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk
from src.knowledge.documents_schema.embeddend_chunk import EmbeddedChunk
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


def make_embedding_result(dense_values=None, sparse_indices=None, sparse_values=None):

    return SimpleNamespace(
        dense=SimpleNamespace(values=dense_values if dense_values is not None else [0.1]),
        sparse=SimpleNamespace(
            indices=sparse_indices if sparse_indices is not None else [],
            values=sparse_values if sparse_values is not None else [],
        ),
    )


def make_pack(pack_id=1, slug="python-pack", domain_slug="python"):
    return SimpleNamespace(id=pack_id, slug=slug, domain=SimpleNamespace(slug=domain_slug))


@pytest.fixture
def mock_deps():
    vector_store = MagicMock()
    vector_store.upsert_batch = AsyncMock()
    vector_store.delete = AsyncMock()

    document_repo = MagicMock()
    document_repo.create = AsyncMock()
    document_repo.update_status = AsyncMock()

    chunk_repo = MagicMock()
    chunk_repo.bulk_create = AsyncMock()

    pack_repo = MagicMock()
    pack_repo.get_by_id = AsyncMock()

    return vector_store, document_repo, chunk_repo, pack_repo


@pytest.fixture
def pipeline(mock_deps):
    vector_store, document_repo, chunk_repo, pack_repo = mock_deps

    with (
        patch(
            "src.knowledge.ingestion.extraction.chunking.tiktoken.get_encoding",
            return_value=MagicMock(),
        ),
        patch("src.knowledge.pipeline.Embedding", return_value=MagicMock()),
        patch("src.knowledge.pipeline.LanguageDetect", return_value=MagicMock()),
        patch("src.knowledge.pipeline.TagExtractor", return_value=MagicMock()),
        patch("src.knowledge.pipeline.QualityScorer", return_value=MagicMock()),
    ):
        instance = IngestionPipeline(
            vector_store=vector_store,
            document_repo=document_repo,
            chunk_repo=chunk_repo,
            pack_repo=pack_repo,
        )

    instance.chunker = MagicMock()
    instance.normalizer = MagicMock()
    instance.validator = MagicMock()
    instance.embedder = MagicMock()
    instance.language_detector = MagicMock()
    instance.tag_extractor = MagicMock()
    instance.quality_scorer = MagicMock()

    instance.language_detector.detect.return_value = "en"
    instance.normalizer.find_boilerplate.return_value = []
    instance.normalizer.normalize.return_value = []
    instance.validator.validate.return_value = True
    instance.tag_extractor.extract_tags.return_value = []
    instance.quality_scorer.score.return_value = 1.0
    instance.quality_scorer.gate.return_value = "normal"

    return instance


class TestGetExtractor:

    def test_delegates_to_extractor_registry(self, pipeline):
        mock_extractor = MagicMock()
        with patch("src.knowledge.pipeline.ExtractorRegistry.create", return_value=mock_extractor) as mock_create:
            result = pipeline._get_extractor("text/plain")

        mock_create.assert_called_once_with("text/plain")
        assert result is mock_extractor

    def test_propagates_error_for_unknown_content_type(self, pipeline):
        with patch(
            "src.knowledge.pipeline.ExtractorRegistry.create",
            side_effect=ValueError("No extractor for content_type: application/unknown"),
        ):
            with pytest.raises(ValueError, match="No extractor for content_type"):
                pipeline._get_extractor("application/unknown")


class TestExtract:

    def test_delegates_to_extractor_for_raw_docs_content_type(self, pipeline):
        raw_doc = make_raw_document(content_type="text/plain")
        expected = ExtractedDocument(text="extracted", metadata={"source": raw_doc.source})

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = expected

        with patch("src.knowledge.pipeline.ExtractorRegistry.create", return_value=mock_extractor) as mock_create:
            result = pipeline._extract(raw_doc)

        mock_create.assert_called_once_with("text/plain")
        mock_extractor.extract.assert_called_once_with(raw_doc)
        assert result is expected


class TestLanguage:

    def test_delegates_to_language_detector(self, pipeline):
        extracted = ExtractedDocument(text="bonjour le monde", metadata={})
        pipeline.language_detector.detect.return_value = "fr"

        result = pipeline._language(extracted)

        pipeline.language_detector.detect.assert_called_once_with("bonjour le monde")
        assert result == "fr"


class TestChunkAndFilter:

    def test_chains_chunker_normalizer_validator_and_quality_gate(self, pipeline):
        extracted = ExtractedDocument(text="text", metadata={})
        chunk_a, chunk_b = make_chunk("a", 0), make_chunk("b", 1)

        pipeline.chunker.chunk.return_value = [chunk_a, chunk_b]
        pipeline.normalizer.find_boilerplate.return_value = ["boilerplate line"]
        pipeline.normalizer.normalize.return_value = [chunk_a, chunk_b]
        pipeline.validator.validate.return_value = True
        pipeline.tag_extractor.extract_tags.return_value = ["tag1"]
        pipeline.quality_scorer.score.return_value = 0.8
        pipeline.quality_scorer.gate.return_value = "normal"

        result = pipeline._chunk_and_filter(extracted, "en")

        pipeline.chunker.chunk.assert_called_once_with(extracted)
        pipeline.normalizer.find_boilerplate.assert_called_once_with([chunk_a, chunk_b])
        pipeline.normalizer.normalize.assert_called_once_with([chunk_a, chunk_b], ["boilerplate line"])
        assert result == [chunk_a, chunk_b]
        for chunk in result:
            assert chunk.metadata["language"] == "en"
            assert chunk.metadata["quality_score"] == 0.8
            assert chunk.metadata["ingestion_priority"] == "normal"
            assert chunk.metadata["tags"] == ["tag1"]

    def test_drops_chunks_that_fail_validation(self, pipeline):
        extracted = ExtractedDocument(text="text", metadata={})
        chunk_a, chunk_b = make_chunk("a", 0), make_chunk("b", 1)

        pipeline.chunker.chunk.return_value = [chunk_a, chunk_b]
        pipeline.normalizer.normalize.return_value = [chunk_a, chunk_b]
        pipeline.validator.validate.side_effect = [True, False]

        result = pipeline._chunk_and_filter(extracted, "en")

        assert result == [chunk_a]

    def test_drops_chunks_rejected_by_quality_gate(self, pipeline):
        extracted = ExtractedDocument(text="text", metadata={})
        chunk_a, chunk_b = make_chunk("a", 0), make_chunk("b", 1)

        pipeline.chunker.chunk.return_value = [chunk_a, chunk_b]
        pipeline.normalizer.normalize.return_value = [chunk_a, chunk_b]
        pipeline.validator.validate.return_value = True
        pipeline.quality_scorer.gate.side_effect = ["normal", "reject"]

        result = pipeline._chunk_and_filter(extracted, "en")

        assert result == [chunk_a]

    def test_returns_empty_list_when_all_chunks_filtered_out(self, pipeline):
        extracted = ExtractedDocument(text="text", metadata={})
        pipeline.chunker.chunk.return_value = [make_chunk("a", 0)]
        pipeline.normalizer.normalize.return_value = [make_chunk("a", 0)]
        pipeline.validator.validate.return_value = False

        result = pipeline._chunk_and_filter(extracted, "en")

        assert result == []


class TestSaveDocument:

    @pytest.mark.asyncio
    async def test_builds_expected_document_create_payload(self, pipeline, mock_deps):
        _, document_repo, _, _ = mock_deps
        raw_doc = make_raw_document(content=b"some file content")
        document_repo.create.return_value = Document(id=1)

        await pipeline._save_document(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=5)

        document_repo.create.assert_awaited_once()
        _, kwargs = document_repo.create.call_args
        assert kwargs["source"] == raw_doc.source
        assert kwargs["content_hash"] == raw_doc.content_hash
        assert kwargs["size"] == len(raw_doc.content)
        assert kwargs["scraped_at"] == raw_doc.fetched_at
        assert kwargs["document_type"] == DocumentType.BOOK
        assert kwargs["knowledge_type"] == KnowledgeType.REFERENCE
        assert kwargs["embedding_model"] == "BAAI/bge-m3"
        assert kwargs["knowledge_pack_id"] == 5

    @pytest.mark.asyncio
    async def test_returns_repo_created_document(self, pipeline, mock_deps):
        _, document_repo, _, _ = mock_deps
        raw_doc = make_raw_document()
        created = Document(id=99)
        document_repo.create.return_value = created

        result = await pipeline._save_document(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=5)

        assert result is created

class TestEmbed:

    def test_returns_empty_list_without_calling_embedder_for_no_chunks(self, pipeline):
        result = pipeline._embed([])

        assert result == []
        pipeline.embedder.embed.assert_not_called()

    def test_calls_embedder_with_chunk_texts_in_order_and_wraps_results(self, pipeline):
        chunks = [make_chunk("first", 0), make_chunk("second", 1)]
        embedding_results = [
            make_embedding_result(dense_values=[0.1], sparse_indices=[1], sparse_values=[0.5]),
            make_embedding_result(dense_values=[0.2], sparse_indices=[2], sparse_values=[0.6]),
        ]
        pipeline.embedder.embed.return_value = embedding_results

        result = pipeline._embed(chunks)

        pipeline.embedder.embed.assert_called_once_with(["first", "second"])
        assert len(result) == 2
        assert all(isinstance(item, EmbeddedChunk) for item in result)
        assert result[0].chunk.text == "first"
        assert result[0].dense_vector == [0.1]
        assert result[0].sparse_indices == [1]
        assert result[0].sparse_values == [0.5]
        assert result[1].chunk.text == "second"
        assert result[1].dense_vector == [0.2]


class TestBuildVectorPoints:

    def test_builds_one_point_per_chunk_with_expected_payload(self, pipeline):
        chunk = make_chunk(
            "hello",
            index=0,
            metadata={"language": "en", "tags": ["greeting"], "quality_score": 0.9},
        )
        embedded_chunk = EmbeddedChunk(chunk=chunk, dense_vector=[0.1, 0.2], sparse_indices=[1], sparse_values=[0.5])

        points = pipeline._build_vector_points(
            [embedded_chunk],
            document_id=42,
            document_type=DocumentType.BOOK,
            pack_slug="python-pack",
            domain_slug="python",
        )

        assert len(points) == 1
        point = points[0]
        assert isinstance(point, VectorPoint)
        expected_id = hashlib.md5("42:0:hello".encode()).hexdigest()
        assert point.id == expected_id
        assert point.dense.values == [0.1, 0.2]
        assert point.sparse.indices == [1]
        assert point.sparse.values == [0.5]
        assert point.payload["document_id"] == 42
        assert point.payload["chunk_index"] == 0
        assert point.payload["text"] == "hello"
        assert point.payload["knowledge_pack"] == "python-pack"
        assert point.payload["domain"] == "python"
        assert point.payload["language"] == "en"
        assert point.payload["source_type"] == DocumentType.BOOK.value
        assert point.payload["tags"] == ["greeting"]
        assert point.payload["quality_score"] == 0.9

    def test_point_ids_are_deterministic_for_same_inputs(self, pipeline):
        chunk = make_chunk("stable text", index=2, metadata={"language": "en", "tags": [], "quality_score": 1.0})
        embedded_chunk = EmbeddedChunk(chunk=chunk, dense_vector=[0.1], sparse_indices=[], sparse_values=[])

        first = pipeline._build_vector_points(
            [embedded_chunk], document_id=5, document_type=DocumentType.BOOK, pack_slug="p", domain_slug="d"
        )
        second = pipeline._build_vector_points(
            [embedded_chunk], document_id=5, document_type=DocumentType.BOOK, pack_slug="p", domain_slug="d"
        )

        assert first[0].id == second[0].id

    def test_missing_metadata_keys_raise_key_error(self, pipeline):
        chunk = make_chunk("no metadata", index=0, metadata={})
        embedded_chunk = EmbeddedChunk(chunk=chunk, dense_vector=[], sparse_indices=[], sparse_values=[])

        with pytest.raises(KeyError):
            pipeline._build_vector_points(
                [embedded_chunk], document_id=1, document_type=DocumentType.BOOK, pack_slug="p", domain_slug="d"
            )


class TestSaveChunk:

    @pytest.mark.asyncio
    async def test_bulk_creates_rows_matching_chunks_and_points(self, pipeline, mock_deps):
        _, _, chunk_repo, _ = mock_deps
        chunk = make_chunk("text", index=0, token_count=7)
        embedded_chunk = EmbeddedChunk(chunk=chunk, dense_vector=[0.1], sparse_indices=[], sparse_values=[])
        point = MagicMock(id="point-id-1")

        await pipeline._save_chunk([embedded_chunk], [point], document_id=3)

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
        _, _, chunk_repo, _ = mock_deps

        await pipeline._save_chunk([], [], document_id=3)

        chunk_repo.bulk_create.assert_awaited_once_with([])

class TestProcess:

    @pytest.mark.asyncio
    async def test_success_path_returns_document_and_marks_indexed(self, pipeline, mock_deps):
        vector_store, document_repo, chunk_repo, pack_repo = mock_deps
        pack_repo.get_by_id.return_value = make_pack()
        raw_doc = make_raw_document(content_type="text/plain")

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = ExtractedDocument(text="some text", metadata={"source": raw_doc.source})

        chunk = make_chunk("chunk text", index=0)
        pipeline.chunker.chunk.return_value = [chunk]
        pipeline.normalizer.normalize.return_value = [chunk]
        pipeline.validator.validate.return_value = True
        pipeline.embedder.embed.return_value = [make_embedding_result()]

        document_repo.create.return_value = Document(id=10)

        with patch("src.knowledge.pipeline.ExtractorRegistry.create", return_value=mock_extractor):
            result = await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=1)

        assert result.id == 10
        vector_store.upsert_batch.assert_awaited_once()
        chunk_repo.bulk_create.assert_awaited_once()
        document_repo.update_status.assert_awaited_once_with(10, DocumentStatus.INDEXED)

    @pytest.mark.asyncio
    async def test_raises_when_knowledge_pack_does_not_exist(self, pipeline, mock_deps):
        _, document_repo, _, pack_repo = mock_deps
        pack_repo.get_by_id.return_value = None
        raw_doc = make_raw_document(content_type="text/plain")

        with pytest.raises(ValueError, match="does not exist"):
            await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=999)

        document_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_content_type_raises_before_saving_document(self, pipeline, mock_deps):
        _, document_repo, _, pack_repo = mock_deps
        pack_repo.get_by_id.return_value = make_pack()
        raw_doc = make_raw_document(content_type="application/unknown")

        with patch(
            "src.knowledge.pipeline.ExtractorRegistry.create",
            side_effect=ValueError("No extractor for content_type: application/unknown"),
        ):
            with pytest.raises(ValueError):
                await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=1)

        document_repo.create.assert_not_awaited()
        document_repo.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_all_chunks_filtered_out_raises_before_saving_document(self, pipeline, mock_deps):
        _, document_repo, _, pack_repo = mock_deps
        pack_repo.get_by_id.return_value = make_pack()
        raw_doc = make_raw_document(content_type="text/plain")

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = ExtractedDocument(text="text", metadata={})
        pipeline.chunker.chunk.return_value = [make_chunk("too short", 0)]
        pipeline.normalizer.normalize.return_value = []

        with patch("src.knowledge.pipeline.ExtractorRegistry.create", return_value=mock_extractor):
            with pytest.raises(ValueError, match="No valid chunks extracted"):
                await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=1)

        document_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_embedding_failure_marks_document_failed_and_reraises(self, pipeline, mock_deps):
        vector_store, document_repo, chunk_repo, pack_repo = mock_deps
        pack_repo.get_by_id.return_value = make_pack()
        raw_doc = make_raw_document(content_type="text/plain")

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = ExtractedDocument(text="text", metadata={})
        chunk = make_chunk("chunk", index=0)
        pipeline.chunker.chunk.return_value = [chunk]
        pipeline.normalizer.normalize.return_value = [chunk]
        pipeline.validator.validate.return_value = True

        pipeline.embedder.embed.side_effect = RuntimeError("embedding backend down")
        document_repo.create.return_value = Document(id=7)

        with patch("src.knowledge.pipeline.ExtractorRegistry.create", return_value=mock_extractor):
            with pytest.raises(RuntimeError, match="embedding backend down"):
                await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=1)

        document_repo.update_status.assert_awaited_once_with(7, DocumentStatus.FAILED)
        vector_store.upsert_batch.assert_not_awaited()
        chunk_repo.bulk_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_vector_store_failure_marks_document_failed_and_reraises(self, pipeline, mock_deps):
        vector_store, document_repo, chunk_repo, pack_repo = mock_deps
        pack_repo.get_by_id.return_value = make_pack()
        raw_doc = make_raw_document(content_type="text/plain")

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = ExtractedDocument(text="text", metadata={})
        chunk = make_chunk("chunk", index=0)
        pipeline.chunker.chunk.return_value = [chunk]
        pipeline.normalizer.normalize.return_value = [chunk]
        pipeline.validator.validate.return_value = True
        pipeline.embedder.embed.return_value = [make_embedding_result()]

        vector_store.upsert_batch.side_effect = ConnectionError("qdrant unreachable")
        document_repo.create.return_value = Document(id=8)

        with patch("src.knowledge.pipeline.ExtractorRegistry.create", return_value=mock_extractor):
            with pytest.raises(ConnectionError, match="qdrant unreachable"):
                await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=1)

        document_repo.update_status.assert_awaited_once_with(8, DocumentStatus.FAILED)
        chunk_repo.bulk_create.assert_not_awaited()
        # upsert never actually succeeded, so no compensating deletes fire
        vector_store.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chunk_repo_failure_rolls_back_upserted_points_marks_failed_and_reraises(self, pipeline, mock_deps):
        vector_store, document_repo, chunk_repo, pack_repo = mock_deps
        pack_repo.get_by_id.return_value = make_pack()
        raw_doc = make_raw_document(content_type="text/plain")

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = ExtractedDocument(text="text", metadata={})
        chunk = make_chunk("chunk", index=0)
        pipeline.chunker.chunk.return_value = [chunk]
        pipeline.normalizer.normalize.return_value = [chunk]
        pipeline.validator.validate.return_value = True
        pipeline.embedder.embed.return_value = [make_embedding_result()]

        chunk_repo.bulk_create.side_effect = RuntimeError("db write failed")
        document_repo.create.return_value = Document(id=9)

        with patch("src.knowledge.pipeline.ExtractorRegistry.create", return_value=mock_extractor):
            with pytest.raises(RuntimeError, match="db write failed"):
                await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=1)

        vector_store.upsert_batch.assert_awaited_once()
        document_repo.update_status.assert_awaited_once_with(9, DocumentStatus.FAILED)
        # points had already been upserted, so the pipeline should roll them back
        vector_store.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_uses_extractor_matching_raw_docs_content_type(self, pipeline, mock_deps):
        _, document_repo, _, pack_repo = mock_deps
        pack_repo.get_by_id.return_value = make_pack()
        raw_doc = make_raw_document(content_type="application/pdf")

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = ExtractedDocument(text="pdf text", metadata={})
        chunk = make_chunk("x", 0)
        pipeline.chunker.chunk.return_value = [chunk]
        pipeline.normalizer.normalize.return_value = [chunk]
        pipeline.validator.validate.return_value = True
        pipeline.embedder.embed.return_value = [make_embedding_result()]
        document_repo.create.return_value = Document(id=12)

        with patch("src.knowledge.pipeline.ExtractorRegistry.create", return_value=mock_extractor) as mock_create:
            await pipeline.process(raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, knowledge_pack_id=1)

        mock_create.assert_called_once_with("application/pdf")