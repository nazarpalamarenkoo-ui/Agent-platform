from unittest.mock import MagicMock

import pytest

from src.rag.retrieval.query_encoder import QueryEncoder
from src.rag.storage.base_vector_store import DenseVector, SparseVector
from src.rag.embeddings.bge_m3 import EmbeddingResult


def make_embedding_result(dense_values=None, sparse_indices=None, sparse_values=None):
    return EmbeddingResult(
        dense=DenseVector(values=dense_values or [0.1, 0.2, 0.3]),
        sparse=SparseVector(indices=sparse_indices or [1, 5], values=sparse_values or [0.5, 0.25]),
    )


@pytest.fixture
def mock_embedding():
    emb = MagicMock()
    emb.embed = MagicMock(return_value=[make_embedding_result()])
    return emb


@pytest.fixture
def query_encoder(mock_embedding):
    return QueryEncoder(embedding=mock_embedding)


class TestQueryEncoderInit:

    def test_stores_embedding(self, mock_embedding):
        encoder = QueryEncoder(embedding=mock_embedding)
        assert encoder.embedding is mock_embedding


class TestEncode:

    def test_wraps_query_in_list_and_calls_embed(self, query_encoder, mock_embedding):
        query_encoder.encode("hello world")

        mock_embedding.embed.assert_called_once_with(["hello world"])

    def test_returns_first_embedding_result(self, query_encoder, mock_embedding):
        expected = make_embedding_result(dense_values=[0.9, 0.8])
        mock_embedding.embed.return_value = [expected]

        result = query_encoder.encode("any query")

        assert result is expected

    def test_result_has_dense_vector(self, query_encoder, mock_embedding):
        mock_embedding.embed.return_value = [make_embedding_result(dense_values=[0.1, 0.2])]

        result = query_encoder.encode("q")

        assert isinstance(result.dense, DenseVector)
        assert result.dense.values == [0.1, 0.2]

    def test_result_has_sparse_vector(self, query_encoder, mock_embedding):
        mock_embedding.embed.return_value = [
            make_embedding_result(sparse_indices=[3, 7], sparse_values=[0.6, 0.4])
        ]

        result = query_encoder.encode("q")

        assert isinstance(result.sparse, SparseVector)
        assert result.sparse.indices == [3, 7]
        assert result.sparse.values == [0.6, 0.4]

    def test_empty_string_query_still_calls_embed(self, query_encoder, mock_embedding):
        query_encoder.encode("")

        mock_embedding.embed.assert_called_once_with([""])

    def test_only_first_result_used_even_if_embed_returns_multiple(
        self, query_encoder, mock_embedding
    ):
        first = make_embedding_result(dense_values=[0.1])
        second = make_embedding_result(dense_values=[0.9])
        mock_embedding.embed.return_value = [first, second]

        result = query_encoder.encode("query")

        assert result is first