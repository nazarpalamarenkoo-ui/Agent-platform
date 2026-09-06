import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.retrieval.retrieval import Retrieval
from src.rag.storage.base_vector_store import VectorSearchResult


def make_result(id_, score=0.0):
    return VectorSearchResult(id=id_, score=score, payload={"text": id_})


@pytest.fixture
def mock_sparse_search():
    search = MagicMock()
    search.search = AsyncMock()
    return search


@pytest.fixture
def mock_dense_search():
    search = MagicMock()
    search.search = AsyncMock()
    return search


@pytest.fixture
def mock_rrf():
    return MagicMock()


@pytest.fixture
def mock_reranker():
    return MagicMock()


@pytest.fixture
def retrieval(mock_sparse_search, mock_dense_search, mock_rrf, mock_reranker):
    return Retrieval(
        sparse_search=mock_sparse_search,
        dense_search=mock_dense_search,
        rrf=mock_rrf,
        reranker=mock_reranker,
    )


class TestRetrieve:

    @pytest.mark.asyncio
    async def test_calls_dense_and_sparse_search_with_query_and_limit(
        self, retrieval, mock_dense_search, mock_sparse_search, mock_rrf, mock_reranker
    ):
        mock_dense_search.search.return_value = []
        mock_sparse_search.search.return_value = []
        mock_rrf.fuse.return_value = []
        mock_reranker.rerank.return_value = []

        await retrieval.retrieve("my query", limit=10, top_n=3)

        mock_dense_search.search.assert_awaited_once_with("my query", 10)
        mock_sparse_search.search.assert_awaited_once_with("my query", 10)

    @pytest.mark.asyncio
    async def test_fuses_dense_and_sparse_results(
        self, retrieval, mock_dense_search, mock_sparse_search, mock_rrf, mock_reranker
    ):
        dense_results = [make_result("a")]
        sparse_results = [make_result("b")]
        mock_dense_search.search.return_value = dense_results
        mock_sparse_search.search.return_value = sparse_results
        mock_rrf.fuse.return_value = []
        mock_reranker.rerank.return_value = []

        await retrieval.retrieve("query", limit=10, top_n=3, k=25)

        mock_rrf.fuse.assert_called_once_with(dense_results, sparse_results, 25)

    @pytest.mark.asyncio
    async def test_default_k_is_sixty(
        self, retrieval, mock_dense_search, mock_sparse_search, mock_rrf, mock_reranker
    ):
        mock_dense_search.search.return_value = []
        mock_sparse_search.search.return_value = []
        mock_rrf.fuse.return_value = []
        mock_reranker.rerank.return_value = []

        await retrieval.retrieve("query", limit=10, top_n=3)

        mock_rrf.fuse.assert_called_once_with([], [], 60)

    @pytest.mark.asyncio
    async def test_reranks_fused_results_and_returns_them(
        self, retrieval, mock_dense_search, mock_sparse_search, mock_rrf, mock_reranker
    ):
        mock_dense_search.search.return_value = []
        mock_sparse_search.search.return_value = []
        fused = [make_result("a"), make_result("b")]
        mock_rrf.fuse.return_value = fused
        reranked = [make_result("b"), make_result("a")]
        mock_reranker.rerank.return_value = reranked

        result = await retrieval.retrieve("query", limit=10, top_n=2)

        mock_reranker.rerank.assert_called_once_with("query", fused, 2)
        assert result == reranked

    @pytest.mark.asyncio
    async def test_dense_and_sparse_searches_run_concurrently(
        self, retrieval, mock_dense_search, mock_sparse_search, mock_rrf, mock_reranker
    ):
        async def slow_search(query, limit):
            await asyncio.sleep(0.05)
            return []

        mock_dense_search.search = AsyncMock(side_effect=slow_search)
        mock_sparse_search.search = AsyncMock(side_effect=slow_search)
        mock_rrf.fuse.return_value = []
        mock_reranker.rerank.return_value = []

        start = asyncio.get_event_loop().time()
        await retrieval.retrieve("query", limit=10, top_n=3)
        elapsed = asyncio.get_event_loop().time() - start

        # if the two searches ran sequentially this would take ~0.1s
        assert elapsed < 0.09

    @pytest.mark.asyncio
    async def test_empty_search_results_still_calls_rrf_and_reranker(
        self, retrieval, mock_dense_search, mock_sparse_search, mock_rrf, mock_reranker
    ):
        mock_dense_search.search.return_value = []
        mock_sparse_search.search.return_value = []
        mock_rrf.fuse.return_value = []
        mock_reranker.rerank.return_value = []

        result = await retrieval.retrieve("query", limit=10, top_n=3)

        mock_rrf.fuse.assert_called_once()
        mock_reranker.rerank.assert_called_once()
        assert result == []