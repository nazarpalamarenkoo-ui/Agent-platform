from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.retrieval.agentic.search.hybrid_search_adapter import HybridSearchAdapter
from src.rag.storage.base_vector_store import VectorSearchResult


@pytest.fixture
def hybrid_retrieval():
    h = MagicMock()
    h.retrieve = AsyncMock(return_value=[])
    return h


@pytest.fixture
def adapter(hybrid_retrieval):
    return HybridSearchAdapter(hybrid_retrieval=hybrid_retrieval)


class TestInit:

    def test_stores_dependency_and_defaults(self, hybrid_retrieval):
        a = HybridSearchAdapter(hybrid_retrieval=hybrid_retrieval)

        assert a.hybrid_retrieval is hybrid_retrieval
        assert a.limit == 20
        assert a.top_n == 5
        assert a.k == 60
        assert a.filters is None

    def test_custom_values(self, hybrid_retrieval):
        filters = SearchFilter(language="en")
        a = HybridSearchAdapter(hybrid_retrieval, limit=7, top_n=2, k=10, filters=filters)

        assert (a.limit, a.top_n, a.k) == (7, 2, 10)
        assert a.filters is filters


class TestSearch:

    async def test_delegates_with_default_params(self, adapter, hybrid_retrieval):
        await adapter.search("my query")

        hybrid_retrieval.retrieve.assert_awaited_once_with(
            query="my query", limit=20, top_n=5, k=60, filters=None
        )

    async def test_uses_configured_params(self, hybrid_retrieval):
        filters = SearchFilter(domains=["engineering"])
        a = HybridSearchAdapter(hybrid_retrieval, limit=7, top_n=2, k=10, filters=filters)

        await a.search("q")

        hybrid_retrieval.retrieve.assert_awaited_once_with(
            query="q", limit=7, top_n=2, k=10, filters=filters
        )

    async def test_returns_results_unchanged(self, adapter, hybrid_retrieval):
        expected = [VectorSearchResult(id="1", score=0.9, payload={"text": "t"})]
        hybrid_retrieval.retrieve.return_value = expected

        assert await adapter.search("q") is expected

    async def test_empty_results(self, adapter):
        assert await adapter.search("q") == []

    async def test_each_call_uses_given_query(self, adapter, hybrid_retrieval):
        await adapter.search("first")
        await adapter.search("second")

        queries = [c.kwargs["query"] for c in hybrid_retrieval.retrieve.await_args_list]
        assert queries == ["first", "second"]

    async def test_propagates_exceptions(self, adapter, hybrid_retrieval):
        hybrid_retrieval.retrieve.side_effect = RuntimeError("qdrant down")

        with pytest.raises(RuntimeError, match="qdrant down"):
            await adapter.search("q")