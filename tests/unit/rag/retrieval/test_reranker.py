from unittest.mock import MagicMock, patch

import pytest

from src.rag.retrieval.reranker import Reranker
from src.rag.storage.base_vector_store import VectorSearchResult


def make_result(id_, text, score=0.0):
    return VectorSearchResult(id=id_, score=score, payload={"text": text})


@pytest.fixture
def reranker():
    with patch("src.rag.retrieval.reranker.FlagReranker") as mock_model_cls:
        instance = Reranker(top_n=5)
        instance.model = MagicMock()
        yield instance


class TestRerankerInit:

    def test_constructs_model_with_expected_kwargs(self):
        with patch("src.rag.retrieval.reranker.FlagReranker") as mock_model_cls:
            Reranker()

        mock_model_cls.assert_called_once_with("BAAI/bge-reranker-v2-m3", use_fp16=True)

    def test_default_top_n_is_five(self):
        with patch("src.rag.retrieval.reranker.FlagReranker"):
            reranker = Reranker()
        assert reranker.top_n == 5

    def test_custom_top_n(self):
        with patch("src.rag.retrieval.reranker.FlagReranker"):
            reranker = Reranker(top_n=3)
        assert reranker.top_n == 3


class TestRerank:

    def test_empty_results_returns_empty_list_without_calling_model(self, reranker):
        result = reranker.rerank("query", [])

        assert result == []
        reranker.model.compute_score.assert_not_called()

    def test_reorders_results_by_score_descending(self, reranker):
        results = [make_result("a", "text a"), make_result("b", "text b"), make_result("c", "text c")]
        reranker.model.compute_score.return_value = [0.2, 0.9, 0.5]

        reranked = reranker.rerank("query", results)

        assert [r.id for r in reranked] == ["b", "c", "a"]
        assert [r.score for r in reranked] == [0.9, 0.5, 0.2]

    def test_passes_query_paired_with_each_results_text_to_model(self, reranker):
        results = [make_result("a", "alpha"), make_result("b", "beta")]
        reranker.model.compute_score.return_value = [0.1, 0.2]

        reranker.rerank("my query", results)

        reranker.model.compute_score.assert_called_once_with(
            [("my query", "alpha"), ("my query", "beta")], normalize=True
        )

    def test_truncates_to_top_n(self, reranker):
        results = [make_result(str(i), f"text {i}") for i in range(5)]
        reranker.model.compute_score.return_value = [0.1, 0.5, 0.9, 0.3, 0.7]

        reranked = reranker.rerank("query", results, top_n=2)

        assert len(reranked) == 2
        assert [r.id for r in reranked] == ["2", "4"]

    def test_uses_instance_top_n_when_not_overridden(self, reranker):
        reranker.top_n = 1
        results = [make_result("a", "a"), make_result("b", "b")]
        reranker.model.compute_score.return_value = [0.1, 0.9]

        reranked = reranker.rerank("query", results)

        assert len(reranked) == 1
        assert reranked[0].id == "b"

    def test_single_pair_returns_float_score_is_wrapped_in_list(self, reranker):
        results = [make_result("only", "only text")]
        reranker.model.compute_score.return_value = 0.42

        reranked = reranker.rerank("query", results)

        assert len(reranked) == 1
        assert reranked[0].score == 0.42

    def test_none_scores_from_model_default_to_zero(self, reranker):
        results = [make_result("a", "a"), make_result("b", "b")]
        reranker.model.compute_score.return_value = None

        reranked = reranker.rerank("query", results)

        assert all(r.score == 0.0 for r in reranked)

    def test_preserves_payload_on_reranked_results(self, reranker):
        results = [make_result("a", "text a")]
        results[0].payload["extra"] = "metadata"
        reranker.model.compute_score.return_value = [0.5]

        reranked = reranker.rerank("query", results)

        assert reranked[0].payload == {"text": "text a", "extra": "metadata"}

    def test_ties_preserve_relative_order_from_sorted_stability(self, reranker):
        results = [make_result("a", "a"), make_result("b", "b")]
        reranker.model.compute_score.return_value = [0.5, 0.5]

        reranked = reranker.rerank("query", results)

        assert [r.id for r in reranked] == ["a", "b"]