from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.tag_repo import TagRepository
from src.services.knowledge_service import KnowledgeService

DOCUMENT_TYPE = list(DocumentType)[0]
KNOWLEDGE_TYPE = list(KnowledgeType)[0]


@pytest.fixture
def corpus_builder():
    return AsyncMock()


@pytest.fixture
def retrieval():
    return AsyncMock()


@pytest.fixture
def service(db_session, corpus_builder, retrieval):
    return KnowledgeService(
        corpus_builder=corpus_builder,
        retrieval=retrieval,
        tag_repo=TagRepository(db_session),
        knowledge_domain_repo=KnowledgeDomainRepository(db_session),
        config_bundle_repo=ConfigBundleRepository(db_session),
    )


class TestIngestFile:
    async def test_delegates_to_corpus_builder_and_returns_its_result(
        self, service, corpus_builder
    ):
        expected = MagicMock()
        corpus_builder.build_from_path.return_value = expected

        result = await service.ingest_file(
            source="new.txt",
            document_type=DOCUMENT_TYPE,
            knowledge_type=KNOWLEDGE_TYPE,
            knowledge_pack_id=1,
        )

        assert result is expected
        corpus_builder.build_from_path.assert_awaited_once_with(
            source_paths=["new.txt"],
            knowledge_pack_id=1,
            document_type=DOCUMENT_TYPE,
            knowledge_type=KNOWLEDGE_TYPE,
        )


class TestIngestFromWeb:
    async def test_delegates_to_corpus_builder_and_returns_its_result(
        self, service, corpus_builder
    ):
        expected = MagicMock()
        corpus_builder.build_from_search.return_value = expected

        result = await service.ingest_from_web(
            query="q",
            document_type=DOCUMENT_TYPE,
            knowledge_type=KNOWLEDGE_TYPE,
            knowledge_pack_id=1,
        )

        assert result is expected
        corpus_builder.build_from_search.assert_awaited_once_with(
            query="q",
            knowledge_pack_id=1,
            document_type=DOCUMENT_TYPE,
            knowledge_type=KNOWLEDGE_TYPE,
        )


class TestSearch:
    async def test_raises_when_config_bundle_missing(self, service, retrieval):
        with pytest.raises(
            ValueError, match="ConfigBundle with id=999999 does not exist"
        ):
            await service.search(
                query="q", limit=5, top_n=5, k=5, config_bundle_id=999_999
            )

        retrieval.retrieve_hybrid.assert_not_called()

    async def test_returns_empty_list_and_skips_retrieval_when_bundle_has_no_packs(
        self, service, sample_config_bundle, retrieval
    ):
        result = await service.search(
            query="q", limit=5, top_n=5, k=5, config_bundle_id=sample_config_bundle.id
        )

        assert result == []
        retrieval.retrieve_hybrid.assert_not_called()

    async def test_delegates_to_hybrid_retrieval_with_pack_slugs_from_the_bundle(
        self,
        service,
        db_session,
        sample_config_bundle,
        sample_knowledge_pack,
        retrieval,
    ):
        await ConfigBundleRepository(db_session).add_knowledge_pack(
            sample_config_bundle, sample_knowledge_pack
        )
        expected_results = [MagicMock()]
        retrieval.retrieve_hybrid.return_value = expected_results

        result = await service.search(
            query="q", limit=5, top_n=3, k=10, config_bundle_id=sample_config_bundle.id
        )

        assert result == expected_results
        retrieval.retrieve_hybrid.assert_awaited_once()

        called_args, _ = retrieval.retrieve_hybrid.call_args
        called_query, called_limit, called_top_n, called_k, called_filters = called_args
        assert called_query == "q"
        assert called_limit == 5
        assert called_top_n == 3
        assert called_k == 10
        assert called_filters.knowledge_packs == [sample_knowledge_pack.slug]
        retrieval.retrieve_agentic.assert_not_called()


class TestSearchAgentic:
    async def test_raises_when_config_bundle_missing(self, service, retrieval):
        with pytest.raises(
            ValueError, match="ConfigBundle with id=999999 does not exist"
        ):
            await service.search_agentic(query="q", config_bundle_id=999_999)

        retrieval.retrieve_agentic.assert_not_called()

    async def test_returns_none_and_skips_retrieval_when_bundle_has_no_packs(
        self, service, sample_config_bundle, retrieval
    ):
        result = await service.search_agentic(
            query="q", config_bundle_id=sample_config_bundle.id
        )

        assert result is None
        retrieval.retrieve_agentic.assert_not_called()

    async def test_delegates_to_agentic_retrieval_with_pack_slugs_from_the_bundle(
        self,
        service,
        db_session,
        sample_config_bundle,
        sample_knowledge_pack,
        retrieval,
    ):
        await ConfigBundleRepository(db_session).add_knowledge_pack(
            sample_config_bundle, sample_knowledge_pack
        )
        expected_context = MagicMock()
        retrieval.retrieve_agentic.return_value = expected_context

        result = await service.search_agentic(
            query="q", config_bundle_id=sample_config_bundle.id
        )

        assert result is expected_context
        retrieval.retrieve_agentic.assert_awaited_once_with(
            "q", knowledge_packs=[sample_knowledge_pack.slug]
        )
        retrieval.retrieve_hybrid.assert_not_called()