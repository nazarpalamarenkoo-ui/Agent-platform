import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge.corpus.builder import CorpusBuilder
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.documents_schema.corpus_build_result import CorpusBuilderResult


DOCUMENT_TYPE = "book"
KNOWLEDGE_TYPE = "reference"
PACK_ID = 1


def make_raw_document(source="https://example.com", content=b"content"):
    return RawDocument(
        source=source,
        content=content,
        content_type="text/html",
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at=datetime.now(timezone.utc),
    )


def make_document(document_id=1):
    document = MagicMock()
    document.id = document_id
    return document


@pytest.fixture
def mock_pipeline():
    return MagicMock()


@pytest.fixture
def mock_orchestrator():
    return MagicMock()


@pytest.fixture
def mock_document_repo():
    return MagicMock()


@pytest.fixture
def builder(mock_pipeline, mock_orchestrator, mock_document_repo):
    return CorpusBuilder(
        pipeline=mock_pipeline,
        orchestrator=mock_orchestrator,
        document_repo=mock_document_repo,
    )


class TestProcessBatch:

    @pytest.mark.asyncio
    async def test_all_new_documents_succeed(self, builder, mock_pipeline, mock_document_repo):
        raw_docs = [
            make_raw_document("https://a.com", b"content a"),
            make_raw_document("https://b.com", b"content b"),
        ]
        mock_document_repo.get_by_hash = AsyncMock(return_value=None)
        mock_pipeline.process = AsyncMock(side_effect=[make_document(1), make_document(2)])

        result = await builder._process_batch(raw_docs, PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert isinstance(result, CorpusBuilderResult)
        assert result.succeeded == [1, 2]
        assert result.skipped_duplicates == []
        assert result.failed == []

    @pytest.mark.asyncio
    async def test_duplicate_by_hash_is_skipped(self, builder, mock_pipeline, mock_document_repo):
        raw_doc = make_raw_document("https://a.com", b"content a")
        mock_document_repo.get_by_hash = AsyncMock(return_value=make_document(99))
        mock_pipeline.process = AsyncMock()

        result = await builder._process_batch([raw_doc], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert result.succeeded == []
        assert result.skipped_duplicates == ["https://a.com"]
        mock_pipeline.process.assert_not_called()

    @pytest.mark.asyncio
    async def test_pipeline_failure_is_recorded_in_failed(self, builder, mock_pipeline, mock_document_repo):
        raw_doc = make_raw_document("https://a.com", b"content a")
        mock_document_repo.get_by_hash = AsyncMock(return_value=None)
        mock_pipeline.process = AsyncMock(side_effect=ValueError("no valid chunks"))

        result = await builder._process_batch([raw_doc], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert result.succeeded == []
        assert result.failed == [{"source": "https://a.com", "error": "no valid chunks"}]

    @pytest.mark.asyncio
    async def test_lookup_failure_is_recorded_in_failed(self, builder, mock_pipeline, mock_document_repo):
        raw_doc = make_raw_document("https://a.com", b"content a")
        mock_document_repo.get_by_hash = AsyncMock(side_effect=ConnectionError("db down"))

        result = await builder._process_batch([raw_doc], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert result.failed == [{"source": "https://a.com", "error": "db down"}]
        mock_pipeline.process.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_batch_partitions_correctly(self, builder, mock_pipeline, mock_document_repo):
        # NOTE: each document needs *distinct* content so their content_hash
        # values differ - otherwise the duplicate-detection stub below can't
        # tell them apart.
        good = make_raw_document("https://good.com", b"good content")
        dup = make_raw_document("https://dup.com", b"duplicate content")
        bad = make_raw_document("https://bad.com", b"bad content")

        async def get_by_hash_side_effect(content_hash):
            if content_hash == dup.content_hash:
                return make_document(5)
            return None

        mock_document_repo.get_by_hash = AsyncMock(side_effect=get_by_hash_side_effect)

        async def process_side_effect(raw_doc, *_args):
            if raw_doc.source == "https://bad.com":
                raise RuntimeError("failed to process")
            return make_document(1)

        mock_pipeline.process = AsyncMock(side_effect=process_side_effect)

        result = await builder._process_batch([good, dup, bad], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert result.succeeded == [1]
        assert result.skipped_duplicates == ["https://dup.com"]
        assert result.failed == [{"source": "https://bad.com", "error": "failed to process"}]

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_result(self, builder, mock_document_repo):
        result = await builder._process_batch([], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert result.succeeded == []
        assert result.skipped_duplicates == []
        assert result.failed == []
        mock_document_repo.get_by_hash.assert_not_called()

    @pytest.mark.asyncio
    async def test_pipeline_called_with_expected_arguments(self, builder, mock_pipeline, mock_document_repo):
        raw_doc = make_raw_document("https://a.com", b"content a")
        mock_document_repo.get_by_hash = AsyncMock(return_value=None)
        mock_pipeline.process = AsyncMock(return_value=make_document(1))

        await builder._process_batch([raw_doc], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        mock_pipeline.process.assert_awaited_once_with(raw_doc, DOCUMENT_TYPE, KNOWLEDGE_TYPE, PACK_ID)


class TestBuildFromPath:

    @pytest.mark.asyncio
    async def test_loads_and_processes_each_path(self, builder, mock_pipeline, mock_document_repo):
        raw_doc_a = make_raw_document("/tmp/a.txt", b"content a")
        raw_doc_b = make_raw_document("/tmp/b.pdf", b"content b")

        loader_a = MagicMock()
        loader_a.load_document.return_value = raw_doc_a
        loader_b = MagicMock()
        loader_b.load_document.return_value = raw_doc_b

        mock_document_repo.get_by_hash = AsyncMock(return_value=None)
        mock_pipeline.process = AsyncMock(side_effect=[make_document(1), make_document(2)])

        with patch(
            "mimetypes.guess_type",
            side_effect=[("text/plain", None), ("application/pdf", None)],
        ), patch(
            "src.knowledge.ingestion.loaders.registry.LoaderRegistry.create",
            side_effect=[loader_a, loader_b],
        ) as mock_create:
            result = await builder.build_from_path(
                ["/tmp/a.txt", "/tmp/b.pdf"], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE
            )

        assert result.succeeded == [1, 2]
        assert mock_create.call_args_list[0].args == ("text/plain",)
        assert mock_create.call_args_list[1].args == ("application/pdf",)

    @pytest.mark.asyncio
    async def test_unresolvable_content_type_is_recorded_as_load_failure(
        self, builder, mock_document_repo
    ):
        mock_document_repo.get_by_hash = AsyncMock(return_value=None)

        with patch("mimetypes.guess_type", return_value=(None, None)):
            result = await builder.build_from_path(
                ["/tmp/unknown"], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE
            )

        assert result.succeeded == []
        assert len(result.failed) == 1
        assert result.failed[0]["source"] == "/tmp/unknown"
        assert "Could not determine content type" in result.failed[0]["error"]

    @pytest.mark.asyncio
    async def test_loader_exception_is_recorded_as_load_failure(
        self, builder, mock_document_repo
    ):
        mock_document_repo.get_by_hash = AsyncMock(return_value=None)

        with patch("mimetypes.guess_type", return_value=("text/plain", None)), patch(
            "src.knowledge.ingestion.loaders.registry.LoaderRegistry.create",
            side_effect=FileNotFoundError("missing"),
        ):
            result = await builder.build_from_path(
                ["/tmp/missing.txt"], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE
            )

        assert result.succeeded == []
        assert result.failed == [{"source": "/tmp/missing.txt", "error": "missing"}]

    @pytest.mark.asyncio
    async def test_load_failures_do_not_block_processing_of_other_paths(
        self, builder, mock_pipeline, mock_document_repo
    ):
        good_doc = make_raw_document("/tmp/good.txt", b"good content")
        good_loader = MagicMock()
        good_loader.load_document.return_value = good_doc

        mock_document_repo.get_by_hash = AsyncMock(return_value=None)
        mock_pipeline.process = AsyncMock(return_value=make_document(1))

        def guess_type_side_effect(path):
            if path == "/tmp/bad":
                return (None, None)
            return ("text/plain", None)

        with patch("mimetypes.guess_type", side_effect=guess_type_side_effect), patch(
            "src.knowledge.ingestion.loaders.registry.LoaderRegistry.create",
            return_value=good_loader,
        ):
            result = await builder.build_from_path(
                ["/tmp/bad", "/tmp/good.txt"], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE
            )

        assert result.succeeded == [1]
        assert len(result.failed) == 1
        assert result.failed[0]["source"] == "/tmp/bad"

    @pytest.mark.asyncio
    async def test_empty_path_list_returns_empty_result(self, builder, mock_document_repo):
        mock_document_repo.get_by_hash = AsyncMock(return_value=None)

        result = await builder.build_from_path([], PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert result.succeeded == []
        assert result.skipped_duplicates == []
        assert result.failed == []


class TestBuildFromSearch:

    @pytest.mark.asyncio
    async def test_orchestrates_then_processes_results(
        self, builder, mock_orchestrator, mock_pipeline, mock_document_repo
    ):
        raw_docs = [make_raw_document("https://a.com", b"content a")]
        mock_orchestrator.orchestrate = AsyncMock(return_value=raw_docs)
        mock_document_repo.get_by_hash = AsyncMock(return_value=None)
        mock_pipeline.process = AsyncMock(return_value=make_document(1))

        result = await builder.build_from_search("query", 5, PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert result.succeeded == [1]
        mock_orchestrator.orchestrate.assert_awaited_once_with("query", 5)

    @pytest.mark.asyncio
    async def test_empty_search_results_return_empty_result(
        self, builder, mock_orchestrator, mock_document_repo
    ):
        mock_orchestrator.orchestrate = AsyncMock(return_value=[])
        mock_document_repo.get_by_hash = AsyncMock(return_value=None)

        result = await builder.build_from_search("query", 5, PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert result.succeeded == []
        assert result.skipped_duplicates == []
        assert result.failed == []

    @pytest.mark.asyncio
    async def test_partial_failures_are_reported(
        self, builder, mock_orchestrator, mock_pipeline, mock_document_repo
    ):
        good = make_raw_document("https://good.com", b"good content")
        bad = make_raw_document("https://bad.com", b"bad content")
        mock_orchestrator.orchestrate = AsyncMock(return_value=[good, bad])
        mock_document_repo.get_by_hash = AsyncMock(return_value=None)

        async def process_side_effect(raw_doc, *_args):
            if raw_doc.source == "https://bad.com":
                raise ValueError("bad content")
            return make_document(1)

        mock_pipeline.process = AsyncMock(side_effect=process_side_effect)

        result = await builder.build_from_search("query", 5, PACK_ID, DOCUMENT_TYPE, KNOWLEDGE_TYPE)

        assert result.succeeded == [1]
        assert result.failed == [{"source": "https://bad.com", "error": "bad content"}]