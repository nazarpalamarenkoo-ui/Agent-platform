import pytest

from src.rag.retrieval.agentic.evaluator.heuristic_evaluator import HeuristicEvaluator
from src.rag.retrieval.agentic.models import RetrievalEvaluation, RetrievalEvidence


def ev(query="q", chunk_id="1", score=0.8):
    return RetrievalEvidence(query=query, chunk_id=chunk_id, score=score, text="t")


@pytest.fixture
def evaluator():
    return HeuristicEvaluator()


class TestInit:

    def test_defaults(self, evaluator):
        assert evaluator.coverage_threshold == 0.5
        assert evaluator.confidence_threshold == 0.5
        assert evaluator.success_threshold == 0.6

    def test_custom_thresholds(self):
        e = HeuristicEvaluator(coverage_threshold=0.1, confidence_threshold=0.2, success_threshold=0.3)
        assert (e.coverage_threshold, e.confidence_threshold, e.success_threshold) == (0.1, 0.2, 0.3)


class TestEmptyEvidence:

    async def test_returns_zeroed_insufficient_evaluation(self, evaluator):
        result = await evaluator.evaluate("q", [])

        assert isinstance(result, RetrievalEvaluation)
        assert result.coverage == 0.0
        assert result.confidence == 0.0
        assert result.redundancy == 0.0
        assert result.sufficient is False
        assert result.missing_topics == []
        assert result.retry_queries == []


class TestCoverage:

    async def test_all_queries_have_good_result(self, evaluator):
        result = await evaluator.evaluate(
            "q", [ev("a", "1", 0.9), ev("b", "2", 0.8)]
        )
        assert result.coverage == 1.0

    async def test_partial_coverage(self, evaluator):
        result = await evaluator.evaluate(
            "q", [ev("a", "1", 0.9), ev("b", "2", 0.1)]
        )
        assert result.coverage == 0.5

    async def test_zero_coverage_when_no_query_beats_threshold(self, evaluator):
        result = await evaluator.evaluate("q", [ev("a", "1", 0.2), ev("b", "2", 0.3)])
        assert result.coverage == 0.0

    async def test_score_equal_to_threshold_does_not_count(self, evaluator):
        result = await evaluator.evaluate("q", [ev("a", "1", 0.5)])
        assert result.coverage == 0.0

    async def test_query_counts_once_if_any_of_its_results_passes(self, evaluator):
        result = await evaluator.evaluate(
            "q", [ev("a", "1", 0.1), ev("a", "2", 0.9), ev("a", "3", 0.2)]
        )
        assert result.coverage == 1.0

    async def test_uses_custom_coverage_threshold(self):
        e = HeuristicEvaluator(coverage_threshold=0.9)
        result = await e.evaluate("q", [ev("a", "1", 0.8)])
        assert result.coverage == 0.0


class TestConfidence:

    async def test_confidence_is_mean_of_all_scores(self, evaluator):
        result = await evaluator.evaluate("q", [ev(chunk_id="1", score=0.9), ev(chunk_id="2", score=0.7)])
        assert result.confidence == pytest.approx(0.8)

    async def test_single_evidence_confidence_equals_score(self, evaluator):
        result = await evaluator.evaluate("q", [ev(score=0.42)])
        assert result.confidence == pytest.approx(0.42)


class TestRedundancy:

    async def test_no_duplicates(self, evaluator):
        result = await evaluator.evaluate("q", [ev(chunk_id="1"), ev(chunk_id="2")])
        assert result.redundancy == 0.0

    async def test_half_duplicates(self, evaluator):
        result = await evaluator.evaluate("q", [ev(chunk_id="1"), ev(chunk_id="1")])
        assert result.redundancy == 0.5

    async def test_mixed_duplicates(self, evaluator):
        evidence = [ev(chunk_id="1"), ev(chunk_id="1"), ev(chunk_id="1"), ev(chunk_id="2")]
        result = await evaluator.evaluate("q", evidence)
        assert result.redundancy == pytest.approx(0.5)


class TestSufficiency:

    async def test_sufficient_when_coverage_and_confidence_high(self, evaluator):
        result = await evaluator.evaluate("q", [ev("a", "1", 0.9), ev("b", "2", 0.8)])
        assert result.sufficient is True

    async def test_insufficient_when_coverage_low(self, evaluator):
        result = await evaluator.evaluate(
            "q", [ev("a", "1", 0.9), ev("b", "2", 0.1), ev("c", "3", 0.1)]
        )
        assert result.coverage == pytest.approx(1 / 3)
        assert result.sufficient is False

    async def test_insufficient_when_confidence_low(self):
        e = HeuristicEvaluator(coverage_threshold=0.1, confidence_threshold=0.5)
        result = await e.evaluate("q", [ev("a", "1", 0.2)])
        assert result.coverage == 1.0
        assert result.confidence == pytest.approx(0.2)
        assert result.sufficient is False

    async def test_coverage_exactly_at_success_threshold_is_insufficient(self, evaluator):
        evidence = [
            ev("a", "1", 0.9), ev("b", "2", 0.9), ev("c", "3", 0.9),
            ev("d", "4", 0.4), ev("e", "5", 0.4),
        ]
        result = await evaluator.evaluate("q", evidence)
        assert result.coverage == 0.6
        assert result.sufficient is False

    async def test_confidence_exactly_at_threshold_is_insufficient(self):
        e = HeuristicEvaluator(coverage_threshold=0.1)
        result = await e.evaluate("q", [ev("a", "1", 0.5)])
        assert result.coverage == 1.0
        assert result.confidence == 0.5
        assert result.sufficient is False

    async def test_custom_success_threshold(self):
        e = HeuristicEvaluator(success_threshold=0.9)
        result = await e.evaluate("q", [ev("a", "1", 0.9), ev("b", "2", 0.1)])
        assert result.sufficient is False


class TestOutputShape:

    async def test_never_proposes_missing_topics_or_retry_queries(self, evaluator):
        result = await evaluator.evaluate("q", [ev("a", "1", 0.1)])

        assert result.sufficient is False
        assert result.missing_topics == []
        assert result.retry_queries == []