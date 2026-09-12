import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.retrieval.retrieval import Retrieval
from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.storage.base_vector_store import DenseVector, SparseVector, VectorSearchResult



def make_result(id_, score=0.0):
    return VectorSearchResult(id=id_, score=score, payload={"text": id_})


def make_encoded_query(dense_values=None, sparse_indices=None, sparse_values=None):
    encoded = MagicMock()
    encoded.dense = DenseVector(values=dense_values or [0.1, 0.2, 0.3])
    encoded.sparse = SparseVector(
        indices=sparse_indices or [1, 5],
        values=sparse_values or [0.5, 0.25],
    )
    return encoded


@pytest.fixture
def mock_query_encoder():
    encoder = MagicMock()
    encoder.encode = MagicMock(return_value=make_encoded_query())
    return encoder


@pytest.fixture
def mock_sparse_search():
    search = MagicMock()
    search.search = AsyncMock(return_value=[])
    return search


@pytest.fixture
def mock_dense_search():
    search = MagicMock()
    search.search = AsyncMock(return_value=[])
    return search


@pytest.fixture
def mock_rrf():
    rrf = MagicMock()
    rrf.fuse = MagicMock(return_value=[])
    return rrf


@pytest.fixture
def mock_reranker():
    reranker = MagicMock()
    reranker.rerank = MagicMock(return_value=[])
    return reranker


@pytest.fixture
def retrieval(mock_query_encoder, mock_sparse_search, mock_dense_search, mock_rrf, mock_reranker):
    return Retrieval(
        query_encoder=mock_query_encoder,
        sparse_search=mock_sparse_search,
        dense_search=mock_dense_search,
        rrf=mock_rrf,
        reranker=mock_reranker,
    )


class TestRetrieve:

    @pytest.mark.asyncio
    async def test_encodes_query_before_searching(
        self, retrieval, mock_query_encoder
    ):
        await retrieval.retrieve("my query", limit=10, top_n=3)

        mock_query_encoder.encode.assert_called_once_with("my query")

    @pytest.mark.asyncio
    async def test_passes_encoded_dense_vector_to_dense_search(
        self, retrieval, mock_query_encoder, mock_dense_search
    ):
        encoded = make_encoded_query(dense_values=[0.9, 0.8])
        mock_query_encoder.encode.return_value = encoded

        await retrieval.retrieve("my query", limit=10, top_n=3)

        mock_dense_search.search.assert_awaited_once_with(
            encoded.dense, 10, None
        )

    @pytest.mark.asyncio
    async def test_passes_encoded_sparse_vector_to_sparse_search(
        self, retrieval, mock_query_encoder, mock_sparse_search
    ):
        encoded = make_encoded_query(sparse_indices=[3, 7], sparse_values=[0.6, 0.4])
        mock_query_encoder.encode.return_value = encoded

        await retrieval.retrieve("my query", limit=10, top_n=3)

        mock_sparse_search.search.assert_awaited_once_with(
            encoded.sparse, 10, None
        )

    @pytest.mark.asyncio
    async def test_passes_filters_to_both_searches(
        self, retrieval, mock_dense_search, mock_sparse_search
    ):
        filters = SearchFilter(language="en", domains=["engineering"])

        await retrieval.retrieve("query", limit=5, top_n=2, filters=filters)

        _, dense_args = mock_dense_search.search.call_args
        _, sparse_args = mock_sparse_search.search.call_args
        # positional args: (vector, limit, filters)
        assert mock_dense_search.search.call_args.args[2] is filters
        assert mock_sparse_search.search.call_args.args[2] is filters

    @pytest.mark.asyncio
    async def test_filters_default_to_none(
        self, retrieval, mock_dense_search, mock_sparse_search
    ):
        await retrieval.retrieve("query", limit=5, top_n=2)

        assert mock_dense_search.search.call_args.args[2] is None
        assert mock_sparse_search.search.call_args.args[2] is None

    @pytest.mark.asyncio
    async def test_fuses_dense_and_sparse_results(
        self, retrieval, mock_dense_search, mock_sparse_search, mock_rrf
    ):
        dense_results = [make_result("a")]
        sparse_results = [make_result("b")]
        mock_dense_search.search.return_value = dense_results
        mock_sparse_search.search.return_value = sparse_results

        await retrieval.retrieve("query", limit=10, top_n=3, k=25)

        mock_rrf.fuse.assert_called_once_with(dense_results, sparse_results, 25)

    @pytest.mark.asyncio
    async def test_default_k_is_sixty(self, retrieval, mock_rrf):
        await retrieval.retrieve("query", limit=10, top_n=3)

        mock_rrf.fuse.assert_called_once_with([], [], 60)

    @pytest.mark.asyncio
    async def test_reranks_fused_results_and_returns_them(
        self, retrieval, mock_rrf, mock_reranker
    ):
        fused = [make_result("a"), make_result("b")]
        reranked = [make_result("b"), make_result("a")]
        mock_rrf.fuse.return_value = fused
        mock_reranker.rerank.return_value = reranked

        result = await retrieval.retrieve("query", limit=10, top_n=2)

        mock_reranker.rerank.assert_called_once_with("query", fused, 2)
        assert result == reranked

    @pytest.mark.asyncio
    async def test_dense_and_sparse_searches_run_concurrently(
        self, retrieval, mock_dense_search, mock_sparse_search
    ):
        async def slow(*_):
            await asyncio.sleep(0.05)
            return []

        mock_dense_search.search = AsyncMock(side_effect=slow)
        mock_sparse_search.search = AsyncMock(side_effect=slow)

        start = asyncio.get_event_loop().time()
        await retrieval.retrieve("query", limit=10, top_n=3)
        elapsed = asyncio.get_event_loop().time() - start

        # sequential would take ~0.1s; concurrent should finish in < 0.09s
        assert elapsed < 0.09

    @pytest.mark.asyncio
    async def test_empty_search_results_still_calls_rrf_and_reranker(
        self, retrieval, mock_rrf, mock_reranker
    ):
        result = await retrieval.retrieve("query", limit=10, top_n=3)

        mock_rrf.fuse.assert_called_once()
        mock_reranker.rerank.assert_called_once()
        assert result == []

    @pytest.mark.asyncio
    async def test_propagates_top_n_to_reranker(
        self, retrieval, mock_reranker
    ):
        await retrieval.retrieve("query", limit=10, top_n=7)

        assert mock_reranker.rerank.call_args.args[2] == 7

    @pytest.mark.asyncio
    async def test_propagates_limit_to_both_searches(
        self, retrieval, mock_dense_search, mock_sparse_search
    ):
        await retrieval.retrieve("query", limit=99, top_n=3)

        assert mock_dense_search.search.call_args.args[1] == 99
        assert mock_sparse_search.search.call_args.args[1] == 99