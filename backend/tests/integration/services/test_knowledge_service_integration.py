from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.knowledge_service import KnowledgeService
from src.repositories.document_repo import DocumentRepository
from src.repositories.tag_repo import TagRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType

DOCUMENT_TYPE = list(DocumentType)[0]
KNOWLEDGE_TYPE = list(KnowledgeType)[0]


def make_raw_doc(content_hash, source="doc.txt"):
    raw_doc = MagicMock()
    raw_doc.content_hash = content_hash
    raw_doc.source = source
    return raw_doc


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
def service(db_session, orchestrator, ingestion_pipeline, retrieval):
    return KnowledgeService(
        orchestrator=orchestrator,
        ingestion_pipeline=ingestion_pipeline,
        retrieval=retrieval,
        document_repo=DocumentRepository(db_session),
        tag_repo=TagRepository(db_session),
        knowledge_domain_repo=KnowledgeDomainRepository(db_session),
        config_bundle_repo=ConfigBundleRepository(db_session),
    )


class TestIngestFile:
    async def test_returns_existing_document_without_calling_pipeline_when_hash_matches(
        self, service, ingestion_pipeline, classified_document
    ):
        raw_doc = make_raw_doc(classified_document.content_hash, source="dup.txt")
        loader = MagicMock()
        loader.load_document.return_value = raw_doc

        with patch(
            "src.services.knowledge_service.LoaderRegistry.create", return_value=loader
        ):
            result = await service.ingest_file(
                source="dup.txt",
                document_type=DOCUMENT_TYPE,
                knowledge_type=KNOWLEDGE_TYPE,
                knowledge_pack_id=1,
            )

        assert result.id == classified_document.id
        ingestion_pipeline.process.assert_not_called()

    async def test_processes_and_returns_new_document_when_hash_not_found(
        self, service, ingestion_pipeline
    ):
        raw_doc = make_raw_doc("brand-new-hash", source="new.txt")
        loader = MagicMock()
        loader.load_document.return_value = raw_doc

        expected_document = MagicMock()
        ingestion_pipeline.process.return_value = expected_document

        with patch(
            "src.services.knowledge_service.LoaderRegistry.create", return_value=loader
        ):
            result = await service.ingest_file(
                source="new.txt",
                document_type=DOCUMENT_TYPE,
                knowledge_type=KNOWLEDGE_TYPE,
                knowledge_pack_id=1,
            )

        assert result is expected_document
        ingestion_pipeline.process.assert_awaited_once_with(
            raw_doc, DOCUMENT_TYPE, KNOWLEDGE_TYPE, 1
        )


class TestIngestFromWeb:
    async def test_skips_existing_survives_failures_and_returns_only_successes(
        self, service, orchestrator, ingestion_pipeline, classified_document
    ):
        existing_raw = make_raw_doc(classified_document.content_hash, source="existing.txt")
        value_error_raw = make_raw_doc("hash-value-error", source="bad-value.txt")
        exception_raw = make_raw_doc("hash-exception", source="bad-exception.txt")
        good_raw = make_raw_doc("hash-good", source="good.txt")

        orchestrator.orchestrate.return_value = [
            existing_raw,
            value_error_raw,
            exception_raw,
            good_raw,
        ]

        good_document = MagicMock()

        async def process_side_effect(raw_doc, *_args, **_kwargs):
            if raw_doc is value_error_raw:
                raise ValueError("bad content")
            if raw_doc is exception_raw:
                raise RuntimeError("boom")
            return good_document

        ingestion_pipeline.process.side_effect = process_side_effect

        result = await service.ingest_from_web(
            query="q",
            limit=4,
            document_type=DOCUMENT_TYPE,
            knowledge_type=KNOWLEDGE_TYPE,
            knowledge_pack_id=1,
        )

        # only the genuinely new + successfully processed doc comes back
        assert result == [good_document]
        # the already-known doc is never even sent to the pipeline...
        # ...but both failure cases are attempted and don't stop the loop
        assert ingestion_pipeline.process.call_count == 3

    async def test_returns_empty_list_when_orchestrator_finds_nothing(
        self, service, orchestrator, ingestion_pipeline
    ):
        orchestrator.orchestrate.return_value = []

        result = await service.ingest_from_web(
            query="q",
            limit=4,
            document_type=DOCUMENT_TYPE,
            knowledge_type=KNOWLEDGE_TYPE,
            knowledge_pack_id=1,
        )

        assert result == []
        ingestion_pipeline.process.assert_not_called()


class TestSearch:
    async def test_raises_when_config_bundle_missing(self, service):
        with pytest.raises(
            ValueError, match="ConfigBundle with id=999999 does not exist"
        ):
            await service.search(query="q", limit=5, top_n=5, k=5, config_bundle_id=999_999)

    async def test_returns_empty_list_and_skips_retrieval_when_bundle_has_no_packs(
        self, service, sample_config_bundle, retrieval
    ):
        result = await service.search(
            query="q", limit=5, top_n=5, k=5, config_bundle_id=sample_config_bundle.id
        )

        assert result == []
        retrieval.retrieve.assert_not_called()

    async def test_delegates_to_retrieval_with_pack_slugs_from_the_bundle(
        self, service, db_session, sample_config_bundle, sample_knowledge_pack, retrieval
    ):
        await ConfigBundleRepository(db_session).add_knowledge_pack(
            sample_config_bundle, sample_knowledge_pack
        )

        expected_results = [MagicMock()]
        retrieval.retrieve.return_value = expected_results

        result = await service.search(
            query="q", limit=5, top_n=3, k=10, config_bundle_id=sample_config_bundle.id
        )

        assert result == expected_results
        retrieval.retrieve.assert_awaited_once()

        called_args, _ = retrieval.retrieve.call_args
        called_query, called_limit, called_top_n, called_k, called_filters = called_args
        assert called_query == "q"
        assert called_limit == 5
        assert called_top_n == 3
        assert called_k == 10
        assert called_filters.knowledge_packs == [sample_knowledge_pack.slug]