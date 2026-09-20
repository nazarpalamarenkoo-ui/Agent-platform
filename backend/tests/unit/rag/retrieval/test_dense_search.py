from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.retrieval.dense_search import DenseSearch
from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.storage.base_vector_store import DenseVector, VectorSearchResult


def make_dense_vector(values=None) -> DenseVector:
    return DenseVector(values=values or [0.1, 0.2, 0.3])


@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.search_dense = AsyncMock()
    return store


@pytest.fixture
def dense_search(mock_vector_store):
    return DenseSearch(vector_store=mock_vector_store)


class TestDenseSearchInit:

    def test_stores_vector_store(self, mock_vector_store):
        search = DenseSearch(vector_store=mock_vector_store)
        assert search.vector_store is mock_vector_store


class TestSearch:

    @pytest.mark.asyncio
    async def test_delegates_to_vector_store_search_dense(
        self, dense_search, mock_vector_store
    ):
        vector = make_dense_vector([0.3, 0.4])
        expected = [VectorSearchResult(id="1", score=0.9, payload={})]
        mock_vector_store.search_dense.return_value = expected

        results = await dense_search.search(vector, limit=5)

        mock_vector_store.search_dense.assert_awaited_once_with(
            vector=vector, limit=5, filters=None
        )
        assert results == expected

    @pytest.mark.asyncio
    async def test_passes_filters_to_vector_store(
        self, dense_search, mock_vector_store
    ):
        vector = make_dense_vector()
        filters = SearchFilter(language="en", domains=["engineering"])
        mock_vector_store.search_dense.return_value = []

        await dense_search.search(vector, limit=10, filters=filters)

        mock_vector_store.search_dense.assert_awaited_once_with(
            vector=vector, limit=10, filters=filters
        )

    @pytest.mark.asyncio
    async def test_filters_default_to_none(self, dense_search, mock_vector_store):
        mock_vector_store.search_dense.return_value = []

        await dense_search.search(make_dense_vector(), limit=5)

        _, kwargs = mock_vector_store.search_dense.call_args
        assert kwargs["filters"] is None

    @pytest.mark.asyncio
    async def test_propagates_limit_to_vector_store(
        self, dense_search, mock_vector_store
    ):
        mock_vector_store.search_dense.return_value = []

        await dense_search.search(make_dense_vector(), limit=42)

        _, kwargs = mock_vector_store.search_dense.call_args
        assert kwargs["limit"] == 42

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_store_returns_nothing(
        self, dense_search, mock_vector_store
    ):
        mock_vector_store.search_dense.return_value = []

        results = await dense_search.search(make_dense_vector(), limit=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_passes_vector_values_unchanged(
        self, dense_search, mock_vector_store
    ):
        vector = DenseVector(values=[0.11, 0.22, 0.33])
        mock_vector_store.search_dense.return_value = []

        await dense_search.search(vector, limit=5)

        _, kwargs = mock_vector_store.search_dense.call_args
        assert kwargs["vector"].values == [0.11, 0.22, 0.33]

    @pytest.mark.asyncio
    async def test_returns_all_results_from_store(
        self, dense_search, mock_vector_store
    ):
        results = [VectorSearchResult(id=str(i), score=float(i), payload={}) for i in range(5)]
        mock_vector_store.search_dense.return_value = results

        returned = await dense_search.search(make_dense_vector(), limit=5)

        assert returned == results