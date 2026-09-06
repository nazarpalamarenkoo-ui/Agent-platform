from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.retrieval.dense_search import DenseSearch
from src.rag.storage.base_vector_store import DenseVector, SparseVector, VectorSearchResult


def make_embedding_result(dense_values=None, sparse_indices=None, sparse_values=None):
    result = MagicMock()
    result.dense = DenseVector(values=dense_values or [0.1, 0.2])
    result.sparse = SparseVector(indices=sparse_indices or [1], values=sparse_values or [0.5])
    return result


@pytest.fixture
def mock_embedding():
    return MagicMock()


@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.search_dense = AsyncMock()
    return store


@pytest.fixture
def dense_search(mock_embedding, mock_vector_store):
    return DenseSearch(embedding=mock_embedding, vector_store=mock_vector_store)


class TestSearch:

    @pytest.mark.asyncio
    async def test_embeds_query_and_searches_dense_vector(self, dense_search, mock_embedding, mock_vector_store):
        embedding_result = make_embedding_result(dense_values=[0.3, 0.4])
        mock_embedding.embed.return_value = [embedding_result]
        expected_results = [VectorSearchResult(id="1", score=0.9, payload={})]
        mock_vector_store.search_dense.return_value = expected_results

        results = await dense_search.search("my query", limit=5)

        mock_embedding.embed.assert_called_once_with(["my query"])
        mock_vector_store.search_dense.assert_awaited_once_with(vector=embedding_result.dense, limit=5)
        assert results == expected_results

    @pytest.mark.asyncio
    async def test_uses_only_first_embedding_result(self, dense_search, mock_embedding, mock_vector_store):
        first = make_embedding_result(dense_values=[0.1])
        second = make_embedding_result(dense_values=[0.9])
        mock_embedding.embed.return_value = [first, second]
        mock_vector_store.search_dense.return_value = []

        await dense_search.search("query", limit=3)

        mock_vector_store.search_dense.assert_awaited_once_with(vector=first.dense, limit=3)

    @pytest.mark.asyncio
    async def test_passes_through_empty_results(self, dense_search, mock_embedding, mock_vector_store):
        mock_embedding.embed.return_value = [make_embedding_result()]
        mock_vector_store.search_dense.return_value = []

        results = await dense_search.search("query", limit=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_propagates_limit_to_vector_store(self, dense_search, mock_embedding, mock_vector_store):
        mock_embedding.embed.return_value = [make_embedding_result()]
        mock_vector_store.search_dense.return_value = []

        await dense_search.search("query", limit=42)

        _, kwargs = mock_vector_store.search_dense.call_args
        assert kwargs["limit"] == 42