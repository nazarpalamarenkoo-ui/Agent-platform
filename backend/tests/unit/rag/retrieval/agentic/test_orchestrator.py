from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.retrieval.agentic.exceptions import LLMClientError, LLMRateLimitError
from src.rag.retrieval.agentic.models import (
    AgenticContext,
    RetrievalEvaluation,
    SearchPlan,
)
from src.rag.retrieval.agentic.orchestrator import AgenticOrchestrator
from src.rag.storage.base_vector_store import VectorSearchResult


def result(id_, score=0.8, text=None):
    return VectorSearchResult(id=id_, score=score, payload={"text": text or f"text-{id_}"})


def evaluation(sufficient=True, retry_queries=None, **overrides):
    data = dict(
        sufficient=sufficient,
        coverage=1.0 if sufficient else 0.3,
        confidence=0.9 if sufficient else 0.3,
        redundancy=0.0,
        missing_topics=[],
        retry_queries=retry_queries or [],
    )
    data.update(overrides)
    return RetrievalEvaluation(**data)


@pytest.fixture
def planner():
    p = MagicMock()
    p.create = AsyncMock(return_value=SearchPlan(subqueries=["sub1", "sub2"], reasoning="r"))
    return p


@pytest.fixture
def evaluator():
    e = MagicMock()
    e.evaluate = AsyncMock(return_value=evaluation(sufficient=True))
    return e


@pytest.fixture
def searcher():
    """Повертає один унікальний chunk на кожен виклик, id залежить від запиту."""
    s = MagicMock()

    async def search(query):
        return [result(f"{query}-chunk")]

    s.search = AsyncMock(side_effect=search)
    return s


@pytest.fixture
def orchestrator(planner, evaluator, searcher):
    return AgenticOrchestrator(planner=planner, evaluator=evaluator, searcher=searcher)


def searched_queries(searcher):
    return [c.args[0] for c in searcher.search.await_args_list]


class TestInit:

    def test_stores_dependencies_and_default_max_iterations(self, planner, evaluator, searcher):
        o = AgenticOrchestrator(planner, evaluator, searcher)

        assert o.planner is planner
        assert o.evaluator is evaluator
        assert o.searcher is searcher
        assert o.max_iterations == 4

    def test_custom_max_iterations(self, planner, evaluator, searcher):
        assert AgenticOrchestrator(planner, evaluator, searcher, max_iterations=2).max_iterations == 2


class TestHappyPath:

    async def test_returns_agentic_context(self, orchestrator):
        ctx = await orchestrator.retrieve("q", ["p"])

        assert isinstance(ctx, AgenticContext)
        assert ctx.original_query == "q"

    async def test_calls_planner_with_query_and_packs(self, orchestrator, planner):
        await orchestrator.retrieve("my query", ["python", "rag"])

        planner.create.assert_awaited_once_with("my query", ["python", "rag"])

    async def test_context_holds_plan_from_planner(self, orchestrator, planner):
        ctx = await orchestrator.retrieve("q", ["p"])

        assert ctx.plan == planner.create.return_value
        assert ctx.plan.subqueries == ["sub1", "sub2"]

    async def test_searches_every_subquery_in_order(self, orchestrator, searcher):
        await orchestrator.retrieve("q", ["p"])

        assert searched_queries(searcher) == ["sub1", "sub2"]

    async def test_collects_evidence_tagged_with_originating_subquery(self, orchestrator):
        ctx = await orchestrator.retrieve("q", ["p"])

        assert [(e.query, e.chunk_id) for e in ctx.evidence] == [
            ("sub1", "sub1-chunk"),
            ("sub2", "sub2-chunk"),
        ]

    async def test_multiple_results_per_subquery_are_all_collected(self, orchestrator, searcher):
        searcher.search = AsyncMock(return_value=[result("a"), result("b"), result("c")])

        ctx = await orchestrator.retrieve("q", ["p"])

        assert len(ctx.evidence) == 6 

    async def test_evidence_preserves_text_score_and_metadata(self, orchestrator, searcher):
        searcher.search = AsyncMock(
            return_value=[VectorSearchResult(id=7, score=0.65, payload={"text": "body", "src": "doc"})]
        )

        ctx = await orchestrator.retrieve("q", ["p"])

        e = ctx.evidence[0]
        assert (e.chunk_id, e.score, e.text) == ("7", 0.65, "body")
        assert e.metadata == {"text": "body", "src": "doc"}

    async def test_evaluator_called_with_original_query_not_subquery(self, orchestrator, evaluator):
        await orchestrator.retrieve("original question", ["p"])

        assert evaluator.evaluate.await_args.args[0] == "original question"

    async def test_sufficient_first_iteration_stops_after_one_round(self, orchestrator, evaluator, searcher):
        ctx = await orchestrator.retrieve("q", ["p"])

        evaluator.evaluate.assert_awaited_once()
        assert searcher.search.await_count == 2
        assert ctx.iteration == 1
        assert len(ctx.iterations) == 1

    async def test_context_evaluation_is_last_evaluation(self, orchestrator, evaluator):
        ev = evaluation(sufficient=True)
        evaluator.evaluate.return_value = ev

        ctx = await orchestrator.retrieve("q", ["p"])

        assert ctx.evaluation is ev

    async def test_iteration_record_contents(self, orchestrator, evaluator):
        ev = evaluation(sufficient=True)
        evaluator.evaluate.return_value = ev

        ctx = await orchestrator.retrieve("q", ["p"])

        rec = ctx.iterations[0]
        assert rec.iteration == 1
        assert rec.subqueries == ["sub1", "sub2"]
        assert rec.new_evidence_count == 2
        assert rec.total_evidence_count == 2
        assert rec.evaluation is ev

    async def test_empty_search_results_yield_empty_evidence(self, orchestrator, searcher):
        searcher.search = AsyncMock(return_value=[])

        ctx = await orchestrator.retrieve("q", ["p"])

        assert ctx.evidence == []
        assert ctx.iterations[0].new_evidence_count == 0


class TestRetryLoop:

    async def test_retries_with_evaluator_retry_queries(self, orchestrator, evaluator, searcher):
        evaluator.evaluate.side_effect = [
            evaluation(sufficient=False, retry_queries=["retry1"]),
            evaluation(sufficient=True),
        ]

        await orchestrator.retrieve("q", ["p"])

        assert searched_queries(searcher) == ["sub1", "sub2", "retry1"]

    async def test_iteration_counter_increments(self, orchestrator, evaluator):
        evaluator.evaluate.side_effect = [
            evaluation(sufficient=False, retry_queries=["r1"]),
            evaluation(sufficient=False, retry_queries=["r2"]),
            evaluation(sufficient=True),
        ]

        ctx = await orchestrator.retrieve("q", ["p"])

        assert ctx.iteration == 3
        assert [r.iteration for r in ctx.iterations] == [1, 2, 3]

    async def test_evidence_accumulates_across_iterations(self, orchestrator, evaluator):
        evaluator.evaluate.side_effect = [
            evaluation(sufficient=False, retry_queries=["retry1"]),
            evaluation(sufficient=True),
        ]

        ctx = await orchestrator.retrieve("q", ["p"])

        assert [e.query for e in ctx.evidence] == ["sub1", "sub2", "retry1"]

    async def test_iteration_records_track_new_and_total_counts(self, orchestrator, evaluator):
        evaluator.evaluate.side_effect = [
            evaluation(sufficient=False, retry_queries=["r1", "r2", "r3"]),
            evaluation(sufficient=True),
        ]

        ctx = await orchestrator.retrieve("q", ["p"])

        first, second = ctx.iterations
        assert (first.new_evidence_count, first.total_evidence_count) == (2, 2)
        assert (second.new_evidence_count, second.total_evidence_count) == (3, 5)
        assert second.subqueries == ["r1", "r2", "r3"]

    async def test_evaluator_receives_cumulative_evidence_each_round(self, orchestrator, evaluator):
        seen_sizes = []

        async def evaluate(query, evidences):
            seen_sizes.append(len(evidences))
            return evaluation(sufficient=len(seen_sizes) >= 2, retry_queries=["retry1"])

        evaluator.evaluate = AsyncMock(side_effect=evaluate)

        await orchestrator.retrieve("q", ["p"])

        assert seen_sizes == [2, 3]

    async def test_each_iteration_record_keeps_its_own_evaluation(self, orchestrator, evaluator):
        first = evaluation(sufficient=False, retry_queries=["r"])
        second = evaluation(sufficient=True)
        evaluator.evaluate.side_effect = [first, second]

        ctx = await orchestrator.retrieve("q", ["p"])

        assert ctx.iterations[0].evaluation is first
        assert ctx.iterations[1].evaluation is second
        assert ctx.evaluation is second


class TestStopConditions:

    async def test_stops_when_no_retry_queries_even_if_insufficient(self, orchestrator, evaluator, searcher):
        evaluator.evaluate.return_value = evaluation(sufficient=False, retry_queries=[])

        ctx = await orchestrator.retrieve("q", ["p"])

        evaluator.evaluate.assert_awaited_once()
        assert searcher.search.await_count == 2
        assert ctx.evaluation.sufficient is False

    async def test_stops_at_max_iterations(self, planner, evaluator, searcher):
        o = AgenticOrchestrator(planner, evaluator, searcher, max_iterations=3)
        evaluator.evaluate.return_value = evaluation(sufficient=False, retry_queries=["again"])

        ctx = await o.retrieve("q", ["p"])

        assert evaluator.evaluate.await_count == 3
        assert ctx.iteration == 3
        assert len(ctx.iterations) == 3

    async def test_default_max_iterations_is_four(self, orchestrator, evaluator):
        evaluator.evaluate.return_value = evaluation(sufficient=False, retry_queries=["again"])

        ctx = await orchestrator.retrieve("q", ["p"])

        assert evaluator.evaluate.await_count == 4
        assert ctx.iteration == 4

    async def test_max_iterations_one_never_retries(self, planner, evaluator, searcher):
        o = AgenticOrchestrator(planner, evaluator, searcher, max_iterations=1)
        evaluator.evaluate.return_value = evaluation(sufficient=False, retry_queries=["again"])

        ctx = await o.retrieve("q", ["p"])

        evaluator.evaluate.assert_awaited_once()
        assert searched_queries(searcher) == ["sub1", "sub2"]
        assert ctx.iteration == 1

    async def test_sufficient_wins_over_retry_queries(self, orchestrator, evaluator):
        evaluator.evaluate.return_value = evaluation(sufficient=True, retry_queries=["ignored"])

        ctx = await orchestrator.retrieve("q", ["p"])

        evaluator.evaluate.assert_awaited_once()
        assert len(ctx.iterations) == 1


class TestEmptyPlan:

    async def test_empty_plan_skips_search_but_still_evaluates(self, orchestrator, planner, evaluator, searcher):
        planner.create.return_value = SearchPlan(subqueries=[])
        evaluator.evaluate.return_value = evaluation(sufficient=False)

        ctx = await orchestrator.retrieve("q", ["p"])

        searcher.search.assert_not_called()
        assert evaluator.evaluate.await_args.args[1] == []
        assert ctx.evidence == []


class TestPlannerRateLimitFallback:

    @pytest.fixture(autouse=True)
    def _rate_limited_planner(self, planner):
        planner.create.side_effect = LLMRateLimitError("limit")

    async def test_falls_back_to_single_hybrid_search_on_original_query(self, orchestrator, searcher):
        await orchestrator.retrieve("original", ["p"])

        assert searched_queries(searcher) == ["original"]

    async def test_does_not_call_evaluator(self, orchestrator, evaluator):
        await orchestrator.retrieve("original", ["p"])

        evaluator.evaluate.assert_not_called()

    async def test_fallback_context_shape(self, orchestrator):
        ctx = await orchestrator.retrieve("original", ["p"])

        assert ctx.original_query == "original"
        assert ctx.plan.subqueries == ["original"]
        assert ctx.evaluation is None
        assert ctx.iteration == 1
        assert ctx.iterations == []

    async def test_fallback_evidence_tagged_with_original_query(self, orchestrator):
        ctx = await orchestrator.retrieve("original", ["p"])

        assert [(e.query, e.chunk_id) for e in ctx.evidence] == [("original", "original-chunk")]


class TestEvaluatorRateLimitFallback:

    async def test_first_iteration_keeps_evidence_and_adds_fallback(self, orchestrator, evaluator):
        evaluator.evaluate.side_effect = LLMRateLimitError("limit")

        ctx = await orchestrator.retrieve("original", ["p"])

        assert [e.query for e in ctx.evidence] == ["sub1", "sub2", "original"]

    async def test_fallback_context_shape(self, orchestrator, evaluator):
        evaluator.evaluate.side_effect = LLMRateLimitError("limit")

        ctx = await orchestrator.retrieve("original", ["p"])

        assert ctx.plan.subqueries == ["original"]
        assert ctx.evaluation is None
        assert ctx.iteration == 1
        assert ctx.iterations == []

    async def test_late_iteration_preserves_all_earlier_evidence(self, orchestrator, evaluator):
        evaluator.evaluate.side_effect = [
            evaluation(sufficient=False, retry_queries=["retry1"]),
            LLMRateLimitError("limit"),
        ]

        ctx = await orchestrator.retrieve("original", ["p"])

        assert [e.query for e in ctx.evidence] == ["sub1", "sub2", "retry1", "original"]
        assert ctx.iterations == []
        assert ctx.evaluation is None

    async def test_does_not_record_failed_iteration(self, orchestrator, evaluator):
        evaluator.evaluate.side_effect = LLMRateLimitError("limit")

        ctx = await orchestrator.retrieve("original", ["p"])

        assert ctx.iterations == []


class TestErrorPropagation:

    async def test_planner_non_rate_limit_error_propagates(self, orchestrator, planner):
        planner.create.side_effect = LLMClientError("api down")

        with pytest.raises(LLMClientError):
            await orchestrator.retrieve("q", ["p"])

    async def test_evaluator_non_rate_limit_error_propagates(self, orchestrator, evaluator):
        evaluator.evaluate.side_effect = LLMClientError("api down")

        with pytest.raises(LLMClientError):
            await orchestrator.retrieve("q", ["p"])

    async def test_searcher_error_propagates(self, orchestrator, searcher):
        searcher.search = AsyncMock(side_effect=RuntimeError("qdrant down"))

        with pytest.raises(RuntimeError, match="qdrant down"):
            await orchestrator.retrieve("q", ["p"])

    async def test_searcher_error_in_fallback_propagates(self, orchestrator, planner, searcher):
        planner.create.side_effect = LLMRateLimitError("limit")
        searcher.search = AsyncMock(side_effect=RuntimeError("qdrant down"))

        with pytest.raises(RuntimeError):
            await orchestrator.retrieve("q", ["p"])


class TestSearchSubqueries:

    async def test_empty_subqueries_returns_empty_list(self, orchestrator, searcher):
        assert await orchestrator._search_subqueries([]) == []
        searcher.search.assert_not_called()

    async def test_searches_sequentially_in_given_order(self, orchestrator, searcher):
        evidence = await orchestrator._search_subqueries(["x", "y", "z"])

        assert searched_queries(searcher) == ["x", "y", "z"]
        assert [e.query for e in evidence] == ["x", "y", "z"]


class TestFallbackToHybrid:

    async def test_without_existing_evidence(self, orchestrator, searcher):
        ctx = await orchestrator._fallback_to_hybrid("q")

        assert [e.query for e in ctx.evidence] == ["q"]
        assert ctx.original_query == "q"

    async def test_existing_evidence_comes_first(self, orchestrator):
        existing = await orchestrator._search_subqueries(["old"])

        ctx = await orchestrator._fallback_to_hybrid("q", existing_evidence=existing)

        assert [e.query for e in ctx.evidence] == ["old", "q"]

    async def test_does_not_mutate_existing_evidence_list(self, orchestrator):
        existing = await orchestrator._search_subqueries(["old"])

        await orchestrator._fallback_to_hybrid("q", existing_evidence=existing)

        assert len(existing) == 1