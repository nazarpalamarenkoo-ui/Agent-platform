from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.rag.embeddings.bge_m3 import Embedding, EmbeddingResult
from src.rag.storage.base_vector_store import DenseVector, SparseVector


@pytest.fixture
def embedding():
    with patch("src.rag.embeddings.bge_m3.BGEM3FlagModel") as mock_model_cls:
        instance = Embedding()
        instance.model = MagicMock()
        yield instance


class TestEmbeddingInit:

    def test_constructs_model_with_expected_kwargs(self):
        with patch("src.rag.embeddings.bge_m3.BGEM3FlagModel") as mock_model_cls:
            Embedding()

        mock_model_cls.assert_called_once_with("BAAI/bge-m3", use_fp16=True, batch_size=512)


class TestEmbed:

    def test_returns_one_result_per_input_with_numpy_dense_vectors(self, embedding):
        embedding.model.encode.return_value = {
            "dense_vecs": [np.array([0.1, 0.2, 0.3])],
            "lexical_weights": [{"10": 0.5, "20": 0.25}],
        }

        results = embedding.embed(["hello world"])

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, EmbeddingResult)
        assert isinstance(result.dense, DenseVector)
        assert result.dense.values == [0.1, 0.2, 0.3]
        assert isinstance(result.sparse, SparseVector)
        assert result.sparse.indices == [10, 20]
        assert result.sparse.values == [0.5, 0.25]

    def test_returns_one_result_per_input_with_plain_list_dense_vectors(self, embedding):
        embedding.model.encode.return_value = {
            "dense_vecs": [[0.4, 0.5]],
            "lexical_weights": [{"1": 0.9}],
        }

        results = embedding.embed(["a query"])

        assert results[0].dense.values == [0.4, 0.5]

    def test_calls_model_encode_with_expected_kwargs(self, embedding):
        embedding.model.encode.return_value = {"dense_vecs": [], "lexical_weights": []}

        embedding.embed(["q1", "q2"])

        embedding.model.encode.assert_called_once_with(
            ["q1", "q2"], return_dense=True, return_sparse=True, return_colbert_vecs=False
        )

    def test_handles_multiple_queries_in_order(self, embedding):
        embedding.model.encode.return_value = {
            "dense_vecs": [np.array([0.1]), np.array([0.2])],
            "lexical_weights": [{"1": 0.1}, {"2": 0.2}],
        }

        results = embedding.embed(["first", "second"])

        assert len(results) == 2
        assert results[0].dense.values == [0.1]
        assert results[1].dense.values == [0.2]
        assert results[0].sparse.indices == [1]
        assert results[1].sparse.indices == [2]

    def test_empty_query_list_returns_empty_results(self, embedding):
        embedding.model.encode.return_value = {"dense_vecs": [], "lexical_weights": []}

        results = embedding.embed([])

        assert results == []

    def test_empty_lexical_weights_produce_empty_sparse_vector(self, embedding):
        embedding.model.encode.return_value = {
            "dense_vecs": [np.array([0.1])],
            "lexical_weights": [{}],
        }

        results = embedding.embed(["q"])

        assert results[0].sparse.indices == []
        assert results[0].sparse.values == []


class TestConvertSparse:

    def test_converts_string_keys_to_ints_and_values_to_floats(self, embedding):
        result = embedding._convert_sparse({"3": "0.5", "7": 0.25})

        assert result.indices == [3, 7]
        assert result.values == [0.5, 0.25]

    def test_handles_already_typed_keys_and_values(self, embedding):
        result = embedding._convert_sparse({5: 0.75})

        assert result.indices == [5]
        assert result.values == [0.75]