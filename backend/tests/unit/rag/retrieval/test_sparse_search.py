from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.retrieval.sparse_search import SparseSearch
from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.storage.base_vector_store import SparseVector, VectorSearchResult


def make_sparse_vector(indices=None, values=None) -> SparseVector:
    return SparseVector(indices=indices or [1, 5], values=values or [0.5, 0.25])


@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.search_sparse = AsyncMock()
    return store


@pytest.fixture
def sparse_search(mock_vector_store):
    return SparseSearch(vector_store=mock_vector_store)


class TestSparseSearchInit:

    def test_stores_vector_store(self, mock_vector_store):
        search = SparseSearch(vector_store=mock_vector_store)
        assert search.vector_store is mock_vector_store


class TestSearch:

    @pytest.mark.asyncio
    async def test_delegates_to_vector_store_search_sparse(
        self, sparse_search, mock_vector_store
    ):
        vector = make_sparse_vector([2, 4], [0.7, 0.3])
        expected = [VectorSearchResult(id="1", score=0.8, payload={})]
        mock_vector_store.search_sparse.return_value = expected

        results = await sparse_search.search(vector, limit=5)

        mock_vector_store.search_sparse.assert_awaited_once_with(
            vector=vector, limit=5, filters=None
        )
        assert results == expected

    @pytest.mark.asyncio
    async def test_passes_filters_to_vector_store(
        self, sparse_search, mock_vector_store
    ):
        vector = make_sparse_vector()
        filters = SearchFilter(language="uk", knowledge_packs=["backend"])
        mock_vector_store.search_sparse.return_value = []

        await sparse_search.search(vector, limit=10, filters=filters)

        mock_vector_store.search_sparse.assert_awaited_once_with(
            vector=vector, limit=10, filters=filters
        )

    @pytest.mark.asyncio
    async def test_filters_default_to_none(self, sparse_search, mock_vector_store):
        mock_vector_store.search_sparse.return_value = []

        await sparse_search.search(make_sparse_vector(), limit=5)

        _, kwargs = mock_vector_store.search_sparse.call_args
        assert kwargs["filters"] is None

    @pytest.mark.asyncio
    async def test_propagates_limit_to_vector_store(
        self, sparse_search, mock_vector_store
    ):
        mock_vector_store.search_sparse.return_value = []

        await sparse_search.search(make_sparse_vector(), limit=42)

        _, kwargs = mock_vector_store.search_sparse.call_args
        assert kwargs["limit"] == 42

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_store_returns_nothing(
        self, sparse_search, mock_vector_store
    ):
        mock_vector_store.search_sparse.return_value = []

        results = await sparse_search.search(make_sparse_vector(), limit=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_passes_vector_unchanged_to_store(
        self, sparse_search, mock_vector_store
    ):
        vector = SparseVector(indices=[10, 20], values=[0.9, 0.1])
        mock_vector_store.search_sparse.return_value = []

        await sparse_search.search(vector, limit=5)

        _, kwargs = mock_vector_store.search_sparse.call_args
        assert kwargs["vector"].indices == [10, 20]
        assert kwargs["vector"].values == [0.9, 0.1]

    @pytest.mark.asyncio
    async def test_returns_all_results_from_store(
        self, sparse_search, mock_vector_store
    ):
        results = [VectorSearchResult(id=str(i), score=float(i), payload={}) for i in range(3)]
        mock_vector_store.search_sparse.return_value = results

        returned = await sparse_search.search(make_sparse_vector(), limit=3)

        assert returned == results