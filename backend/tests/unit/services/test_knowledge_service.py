from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.knowledge_service import KnowledgeService


@pytest.fixture
def corpus_builder():
    return AsyncMock()


@pytest.fixture
def retrieval():
    return AsyncMock()


@pytest.fixture
def config_bundle_repo():
    return AsyncMock()


@pytest.fixture
def service(corpus_builder, retrieval, config_bundle_repo):
    return KnowledgeService(
        corpus_builder=corpus_builder,
        retrieval=retrieval,
        tag_repo=AsyncMock(),
        knowledge_domain_repo=AsyncMock(),
        config_bundle_repo=config_bundle_repo,
    )


def make_bundle(*slugs):
    return MagicMock(knowledge_packs=[MagicMock(slug=slug) for slug in slugs])


class TestIngestFile:
    async def test_delegates_to_build_from_path_with_single_source(self, service, corpus_builder):
        expected = MagicMock()
        corpus_builder.build_from_path.return_value = expected

        result = await service.ingest_file("file.pdf", "dt", "kt", 1)

        assert result is expected
        corpus_builder.build_from_path.assert_awaited_once_with(
            source_paths=["file.pdf"], knowledge_pack_id=1, document_type="dt", knowledge_type="kt"
        )
        corpus_builder.build_from_search.assert_not_called()

    async def test_propagates_errors(self, service, corpus_builder):
        corpus_builder.build_from_path.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await service.ingest_file("file.pdf", "dt", "kt", 1)


class TestIngestFromWeb:
    async def test_delegates_to_build_from_search(self, service, corpus_builder):
        expected = MagicMock()
        corpus_builder.build_from_search.return_value = expected

        result = await service.ingest_from_web("some query", "dt", "kt", 7)

        assert result is expected
        corpus_builder.build_from_search.assert_awaited_once_with(
            query="some query", knowledge_pack_id=7, document_type="dt", knowledge_type="kt"
        )
        corpus_builder.build_from_path.assert_not_called()

    async def test_propagates_errors(self, service, corpus_builder):
        corpus_builder.build_from_search.side_effect = ValueError("bad query")

        with pytest.raises(ValueError, match="bad query"):
            await service.ingest_from_web("q", "dt", "kt", 1)


class TestResolvePackSlugs:
    async def test_returns_slugs_in_bundle_order(self, service, config_bundle_repo):
        config_bundle_repo.get_unscoped_with_relations.return_value = make_bundle("b", "a", "c")

        assert await service._resolve_pack_slugs(1) == ["b", "a", "c"]
        config_bundle_repo.get_unscoped_with_relations.assert_awaited_once_with(1)

    async def test_raises_when_bundle_not_found(self, service, config_bundle_repo):
        config_bundle_repo.get_unscoped_with_relations.return_value = None

        with pytest.raises(ValueError, match="ConfigBundle with id=42 does not exist"):
            await service._resolve_pack_slugs(42)


class TestSearch:
    async def test_raises_when_bundle_not_found(self, service, config_bundle_repo, retrieval):
        config_bundle_repo.get_unscoped_with_relations.return_value = None

        with pytest.raises(ValueError, match="ConfigBundle with id=1 does not exist"):
            await service.search("q", 10, 5, 3, config_bundle_id=1)

        retrieval.retrieve_hybrid.assert_not_awaited()

    async def test_empty_when_bundle_has_no_packs(self, service, config_bundle_repo, retrieval):
        config_bundle_repo.get_unscoped_with_relations.return_value = make_bundle()

        assert await service.search("q", 10, 5, 3, config_bundle_id=1) == []
        retrieval.retrieve_hybrid.assert_not_awaited()

    async def test_calls_hybrid_retrieval_with_bundle_slugs(self, service, config_bundle_repo, retrieval):
        config_bundle_repo.get_unscoped_with_relations.return_value = make_bundle("pack-a", "pack-b")
        expected = [MagicMock()]
        retrieval.retrieve_hybrid.return_value = expected

        result = await service.search("q", 10, 5, 3, config_bundle_id=1)

        assert result is expected
        query, limit, top_n, k, search_filter = retrieval.retrieve_hybrid.call_args.args
        assert (query, limit, top_n, k) == ("q", 10, 5, 3)
        assert search_filter.knowledge_packs == ["pack-a", "pack-b"]
        retrieval.retrieve_agentic.assert_not_awaited()

    async def test_propagates_retrieval_errors(self, service, config_bundle_repo, retrieval):
        config_bundle_repo.get_unscoped_with_relations.return_value = make_bundle("p")
        retrieval.retrieve_hybrid.side_effect = RuntimeError("vector store down")

        with pytest.raises(RuntimeError, match="vector store down"):
            await service.search("q", 1, 1, 1, config_bundle_id=1)


class TestSearchAgentic:
    async def test_raises_when_bundle_not_found(self, service, config_bundle_repo, retrieval):
        config_bundle_repo.get_unscoped_with_relations.return_value = None

        with pytest.raises(ValueError, match="ConfigBundle with id=1 does not exist"):
            await service.search_agentic("q", 1)

        retrieval.retrieve_agentic.assert_not_awaited()

    async def test_none_when_bundle_has_no_packs(self, service, config_bundle_repo, retrieval):
        config_bundle_repo.get_unscoped_with_relations.return_value = make_bundle()

        assert await service.search_agentic("q", 1) is None
        retrieval.retrieve_agentic.assert_not_awaited()

    async def test_calls_agentic_retrieval_with_slugs(self, service, config_bundle_repo, retrieval):
        config_bundle_repo.get_unscoped_with_relations.return_value = make_bundle("pack-a", "pack-b")
        expected = MagicMock()
        retrieval.retrieve_agentic.return_value = expected

        result = await service.search_agentic("q", 1)

        assert result is expected
        retrieval.retrieve_agentic.assert_awaited_once_with("q", knowledge_packs=["pack-a", "pack-b"])
        retrieval.retrieve_hybrid.assert_not_awaited()


class TestSearchBySlugs:
    async def test_empty_slugs_short_circuit(self, service, retrieval, config_bundle_repo):
        assert await service.search_by_slugs("q", [], 10, 5, 3) == []

        retrieval.retrieve_hybrid.assert_not_awaited()
        config_bundle_repo.get_unscoped_with_relations.assert_not_awaited()

    async def test_calls_hybrid_retrieval_with_given_slugs(self, service, retrieval):
        expected = [MagicMock()]
        retrieval.retrieve_hybrid.return_value = expected

        result = await service.search_by_slugs("q", ["a", "b"], 10, 5, 3)

        assert result is expected
        query, limit, top_n, k, search_filter = retrieval.retrieve_hybrid.call_args.args
        assert (query, limit, top_n, k) == ("q", 10, 5, 3)
        assert search_filter.knowledge_packs == ["a", "b"]

    async def test_does_not_share_slug_list_with_filter(self, service, retrieval):
        slugs = ["a"]

        await service.search_by_slugs("q", slugs, 1, 1, 1)

        slugs.append("mutated")
        search_filter = retrieval.retrieve_hybrid.call_args.args[4]
        assert search_filter.knowledge_packs == ["a"]