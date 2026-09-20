from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services import knowledge_service as knowledge_module
from src.services.knowledge_service import KnowledgeService


@pytest.fixture
def orchestrator():
    return AsyncMock()


@pytest.fixture
def ingestion_pipeline():
    return AsyncMock()


@pytest.fixture
def retrieval():
    return AsyncMock()


@pytest.fixture
def document_repo():
    return AsyncMock()


@pytest.fixture
def tag_repo():
    return AsyncMock()


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def config_bundle_repo():
    return AsyncMock()


@pytest.fixture
def service(
    orchestrator,
    ingestion_pipeline,
    retrieval,
    document_repo,
    tag_repo,
    domain_repo,
    config_bundle_repo,
):
    return KnowledgeService(
        orchestrator=orchestrator,
        ingestion_pipeline=ingestion_pipeline,
        retrieval=retrieval,
        document_repo=document_repo,
        tag_repo=tag_repo,
        knowledge_domain_repo=domain_repo,
        config_bundle_repo=config_bundle_repo,
    )


class TestIngestFile:
    async def test_returns_existing_document_when_hash_already_known(
        self, service, document_repo, monkeypatch
    ):
        loader = MagicMock()
        raw_doc = MagicMock(content_hash="abc123")
        loader.load_document.return_value = raw_doc
        monkeypatch.setattr(
            knowledge_module.LoaderRegistry, "create", lambda mime: loader
        )
        existing = MagicMock()
        document_repo.get_by_hash.return_value = existing

        result = await service.ingest_file(
            source="file.pdf",
            document_type="doc_type",
            knowledge_type="knowledge_type",
            knowledge_pack_id=1,
        )

        assert result is existing
        document_repo.get_by_hash.assert_awaited_once_with("abc123")

    async def test_processes_new_document_when_not_seen_before(
        self, service, document_repo, ingestion_pipeline, monkeypatch
    ):
        loader = MagicMock()
        raw_doc = MagicMock(content_hash="new-hash")
        loader.load_document.return_value = raw_doc
        monkeypatch.setattr(
            knowledge_module.LoaderRegistry, "create", lambda mime: loader
        )
        document_repo.get_by_hash.return_value = None
        processed = MagicMock()
        ingestion_pipeline.process.return_value = processed

        result = await service.ingest_file(
            source="file.pdf",
            document_type="doc_type",
            knowledge_type="knowledge_type",
            knowledge_pack_id=1,
        )

        assert result is processed
        ingestion_pipeline.process.assert_awaited_once_with(
            raw_doc, "doc_type", "knowledge_type", 1
        )


class TestIngestFromWeb:
    async def test_skips_already_ingested_documents(
        self, service, orchestrator, document_repo, ingestion_pipeline
    ):
        existing_doc = MagicMock(content_hash="dup", source="dup-src")
        orchestrator.orchestrate.return_value = [existing_doc]
        document_repo.get_by_hash.return_value = MagicMock()

        result = await service.ingest_from_web(
            query="q", limit=5, document_type="dt", knowledge_type="kt",
            knowledge_pack_id=1,
        )

        assert result == []
        ingestion_pipeline.process.assert_not_awaited()

    async def test_collects_successfully_ingested_documents(
        self, service, orchestrator, document_repo, ingestion_pipeline
    ):
        raw_doc = MagicMock(content_hash="new", source="new-src")
        orchestrator.orchestrate.return_value = [raw_doc]
        document_repo.get_by_hash.return_value = None
        processed = MagicMock()
        ingestion_pipeline.process.return_value = processed

        result = await service.ingest_from_web(
            query="q", limit=5, document_type="dt", knowledge_type="kt",
            knowledge_pack_id=1,
        )

        assert result == [processed]

    async def test_skips_document_on_value_error_and_continues(
        self, service, orchestrator, document_repo, ingestion_pipeline
    ):
        bad_doc = MagicMock(content_hash="bad", source="bad-src")
        good_doc = MagicMock(content_hash="good", source="good-src")
        orchestrator.orchestrate.return_value = [bad_doc, good_doc]
        document_repo.get_by_hash.return_value = None

        good_result = MagicMock()

        async def process_side_effect(raw_doc, *args, **kwargs):
            if raw_doc is bad_doc:
                raise ValueError("bad document")
            return good_result

        ingestion_pipeline.process.side_effect = process_side_effect

        result = await service.ingest_from_web(
            query="q", limit=5, document_type="dt", knowledge_type="kt",
            knowledge_pack_id=1,
        )

        assert result == [good_result]

    async def test_skips_document_on_unexpected_exception_and_continues(
        self, service, orchestrator, document_repo, ingestion_pipeline
    ):
        bad_doc = MagicMock(content_hash="bad", source="bad-src")
        good_doc = MagicMock(content_hash="good", source="good-src")
        orchestrator.orchestrate.return_value = [bad_doc, good_doc]
        document_repo.get_by_hash.return_value = None

        good_result = MagicMock()

        async def process_side_effect(raw_doc, *args, **kwargs):
            if raw_doc is bad_doc:
                raise RuntimeError("boom")
            return good_result

        ingestion_pipeline.process.side_effect = process_side_effect

        result = await service.ingest_from_web(
            query="q", limit=5, document_type="dt", knowledge_type="kt",
            knowledge_pack_id=1,
        )

        assert result == [good_result]

    async def test_returns_empty_list_when_no_docs_found(
        self, service, orchestrator
    ):
        orchestrator.orchestrate.return_value = []

        result = await service.ingest_from_web(
            query="q", limit=5, document_type="dt", knowledge_type="kt",
            knowledge_pack_id=1,
        )

        assert result == []


class TestSearch:
    async def test_raises_when_config_bundle_not_found(
        self, service, config_bundle_repo
    ):
        config_bundle_repo.get_by_id_with_relations.return_value = None

        with pytest.raises(
            ValueError, match="ConfigBundle with id=1 does not exist"
        ):
            await service.search(
                query="q", limit=10, top_n=5, k=3, config_bundle_id=1
            )

    async def test_returns_empty_list_when_bundle_has_no_packs(
        self, service, config_bundle_repo, retrieval
    ):
        config = MagicMock(knowledge_packs=[])
        config_bundle_repo.get_by_id_with_relations.return_value = config

        result = await service.search(
            query="q", limit=10, top_n=5, k=3, config_bundle_id=1
        )

        assert result == []
        retrieval.retrieve.assert_not_awaited()

    async def test_retrieves_using_pack_slugs_from_bundle(
        self, service, config_bundle_repo, retrieval
    ):
        pack_a = MagicMock(slug="pack-a")
        pack_b = MagicMock(slug="pack-b")
        config = MagicMock(knowledge_packs=[pack_a, pack_b])
        config_bundle_repo.get_by_id_with_relations.return_value = config
        expected = [MagicMock()]
        retrieval.retrieve.return_value = expected

        result = await service.search(
            query="q", limit=10, top_n=5, k=3, config_bundle_id=1
        )

        assert result is expected
        args, _ = retrieval.retrieve.call_args
        query, limit, top_n, k, search_filter = args
        assert query == "q"
        assert limit == 10
        assert top_n == 5
        assert k == 3
        assert search_filter.knowledge_packs == ["pack-a", "pack-b"]