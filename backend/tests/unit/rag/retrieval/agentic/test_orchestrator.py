import itertools
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


def always_insufficient_with_fresh_retries(evaluator):
    """Кожна оцінка: недостатньо + новий унікальний retry-запит (інакше цикл зупиняється)."""
    counter = itertools.count(1)

    async def evaluate(query, evidences):
        return evaluation(sufficient=False, retry_queries=[f"again-{next(counter)}"])

    evaluator.evaluate = AsyncMock(side_effect=evaluate)


class TestInit:

    def test_stores_dependencies_and_defaults(self, planner, evaluator, searcher):
        o = AgenticOrchestrator(planner, evaluator, searcher)

        assert o.planner is planner
        assert o.evaluator is evaluator
        assert o.searcher is searcher
        assert o.max_iterations == 4
        assert o.original_share == 0.6
        assert o.anchor_top_n == 3
        assert o.rrf_k == 60

    def test_custom_max_iterations(self, planner, evaluator, searcher):
        assert AgenticOrchestrator(planner, evaluator, searcher, max_iterations=2).max_iterations == 2

    @pytest.mark.parametrize("share", [0.0, 1.0, -0.1, 1.5])
    def test_rejects_original_share_out_of_range(self, planner, evaluator, searcher, share):
        with pytest.raises(ValueError, match="original_share"):
            AgenticOrchestrator(planner, evaluator, searcher, original_share=share)


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

    async def test_original_query_is_searched_first_then_subqueries(self, orchestrator, searcher):
        await orchestrator.retrieve("q", ["p"])

        assert searched_queries(searcher) == ["q", "sub1", "sub2"]

    async def test_collects_evidence_tagged_with_originating_query(self, orchestrator):
        ctx = await orchestrator.retrieve("q", ["p"])

        assert [(e.query, e.chunk_id) for e in ctx.evidence] == [
            ("q", "q-chunk"),
            ("sub1", "sub1-chunk"),
            ("sub2", "sub2-chunk"),
        ]

    async def test_raw_evidence_keeps_every_hit_with_original_score(self, orchestrator, searcher):
        searcher.search = AsyncMock(return_value=[result("a"), result("b"), result("c")])

        ctx = await orchestrator.retrieve("q", ["p"])

        assert len(ctx.raw_evidence) == 9
        assert all(e.score == 0.8 and e.raw_score is None for e in ctx.raw_evidence)

    async def test_evidence_is_deduplicated_by_chunk_id(self, orchestrator, searcher):
        searcher.search = AsyncMock(return_value=[result("a"), result("b"), result("c")])

        ctx = await orchestrator.retrieve("q", ["p"])

        assert [e.chunk_id for e in ctx.evidence] == ["a", "b", "c"]

    async def test_evidence_has_fused_score_and_keeps_raw_score(self, orchestrator, searcher):
        searcher.search = AsyncMock(
            return_value=[VectorSearchResult(id=7, score=0.65, payload={"text": "body", "src": "doc"})]
        )

        ctx = await orchestrator.retrieve("q", ["p"])

        e = ctx.evidence[0]
        assert (e.chunk_id, e.text, e.raw_score) == ("7", "body", 0.65)
        assert e.metadata == {"text": "body", "src": "doc"}
        assert e.score == pytest.approx(5 / 61)

    async def test_evaluator_called_with_original_query_not_subquery(self, orchestrator, evaluator):
        await orchestrator.retrieve("original question", ["p"])

        assert evaluator.evaluate.await_args.args[0] == "original question"

    async def test_sufficient_first_iteration_stops_after_one_round(
        self, orchestrator, evaluator, searcher
    ):
        ctx = await orchestrator.retrieve("q", ["p"])

        evaluator.evaluate.assert_awaited_once()
        assert searcher.search.await_count == 3
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
        assert rec.subqueries == ["q", "sub1", "sub2"]
        assert rec.new_evidence_count == 3
        assert rec.total_evidence_count == 3
        assert rec.new_unique_count == 3
        assert rec.total_unique_count == 3
        assert rec.evaluation is ev

    async def test_empty_search_results_yield_empty_evidence(self, orchestrator, searcher):
        searcher.search = AsyncMock(return_value=[])

        ctx = await orchestrator.retrieve("q", ["p"])

        assert ctx.evidence == []
        assert ctx.raw_evidence == []
        assert ctx.iterations[0].new_evidence_count == 0
        assert ctx.iterations[0].new_unique_count == 0


class TestQueryDeduplication:

    async def test_subquery_equal_to_original_is_not_searched_twice(
        self, orchestrator, planner, searcher
    ):
        planner.create.return_value = SearchPlan(subqueries=["  Q ", "sub1"])

        await orchestrator.retrieve("q", ["p"])

        assert searched_queries(searcher) == ["q", "sub1"]

    async def test_repeated_subqueries_are_searched_once_ignoring_case_and_spaces(
        self, orchestrator, planner, searcher
    ):
        planner.create.return_value = SearchPlan(subqueries=["sub1", "SUB1", "sub1  "])

        await orchestrator.retrieve("q", ["p"])

        assert searched_queries(searcher) == ["q", "sub1"]

    def test_fresh_queries_drops_already_searched(self):
        assert AgenticOrchestrator._fresh_queries(["a", "b"], {"a"}) == ["b"]

    def test_fresh_queries_drops_blank_and_duplicates(self):
        assert AgenticOrchestrator._fresh_queries(["x", " ", "", "X", "y"], set()) == ["x", "y"]

    def test_fresh_queries_preserves_original_spelling(self):
        assert AgenticOrchestrator._fresh_queries(["Hello  World"], set()) == ["Hello  World"]


class TestFusion:

    async def test_original_top_chunks_are_anchored_ahead_of_consensus(self, planner, evaluator):
        async def search(query):
            if query == "q":
                return [result(i) for i in ("a", "b", "c", "d")]
            return [result("x")]

        searcher = MagicMock()
        searcher.search = AsyncMock(side_effect=search)
        o = AgenticOrchestrator(planner, evaluator, searcher, original_share=0.3, anchor_top_n=3)

        ctx = await o.retrieve("q", ["p"])

        assert [e.chunk_id for e in ctx.evidence] == ["a", "b", "c", "x", "d"]

    async def test_chunk_found_by_several_queries_outranks_single_hit(self, planner, evaluator):
        async def search(query):
            if query == "q":
                return [result("a")]
            if query == "sub1":
                return [result("b"), result("c")]
            return [result("c")]

        searcher = MagicMock()
        searcher.search = AsyncMock(side_effect=search)
        o = AgenticOrchestrator(planner, evaluator, searcher, anchor_top_n=1)

        ctx = await o.retrieve("q", ["p"])

        assert [e.chunk_id for e in ctx.evidence] == ["a", "c", "b"]

    def test_fuse_of_nothing_is_empty(self, orchestrator):
        assert orchestrator._fuse([]) == []


class TestRetryLoop:

    async def test_retries_with_evaluator_retry_queries(self, orchestrator, evaluator, searcher):
        evaluator.evaluate.side_effect = [
            evaluation(sufficient=False, retry_queries=["retry1"]),
            evaluation(sufficient=True),
        ]

        await orchestrator.retrieve("q", ["p"])

        assert searched_queries(searcher) == ["q", "sub1", "sub2", "retry1"]

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

        assert [e.query for e in ctx.evidence] == ["q", "sub1", "sub2", "retry1"]

    async def test_iteration_records_track_new_and_total_counts(self, orchestrator, evaluator):
        evaluator.evaluate.side_effect = [
            evaluation(sufficient=False, retry_queries=["r1", "r2", "r3"]),
            evaluation(sufficient=True),
        ]

        ctx = await orchestrator.retrieve("q", ["p"])

        first, second = ctx.iterations
        assert (first.new_evidence_count, first.total_evidence_count) == (3, 3)
        assert (first.new_unique_count, first.total_unique_count) == (3, 3)
        assert (second.new_evidence_count, second.total_evidence_count) == (3, 6)
        assert (second.new_unique_count, second.total_unique_count) == (3, 6)
        assert second.subqueries == ["r1", "r2", "r3"]

    async def test_already_searched_retry_queries_are_dropped_from_the_round(
        self, orchestrator, evaluator, searcher
    ):
        evaluator.evaluate.side_effect = [
            evaluation(sufficient=False, retry_queries=["sub1", "new"]),
            evaluation(sufficient=True),
        ]

        ctx = await orchestrator.retrieve("q", ["p"])

        assert searched_queries(searcher) == ["q", "sub1", "sub2", "new"]
        assert ctx.iterations[1].subqueries == ["new"]

    async def test_evaluator_receives_cumulative_evidence_each_round(self, orchestrator, evaluator):
        seen_sizes = []

        async def evaluate(query, evidences):
            seen_sizes.append(len(evidences))
            return evaluation(sufficient=len(seen_sizes) >= 2, retry_queries=["retry1"])

        evaluator.evaluate = AsyncMock(side_effect=evaluate)

        await orchestrator.retrieve("q", ["p"])

        assert seen_sizes == [3, 4]

    async def test_each_iteration_record_keeps_its_own_evaluation(self, orchestrator, evaluator):
        first = evaluation(sufficient=False, retry_queries=["r"])
        second = evaluation(sufficient=True)
        evaluator.evaluate.side_effect = [first, second]

        ctx = await orchestrator.retrieve("q", ["p"])

        assert ctx.iterations[0].evaluation is first
        assert ctx.iterations[1].evaluation is second
        assert ctx.evaluation is second


class TestStopConditions:

    async def test_stops_when_no_retry_queries_even_if_insufficient(
        self, orchestrator, evaluator, searcher
    ):
        evaluator.evaluate.return_value = evaluation(sufficient=False, retry_queries=[])

        ctx = await orchestrator.retrieve("q", ["p"])

        evaluator.evaluate.assert_awaited_once()
        assert searcher.search.await_count == 3
        assert ctx.evaluation.sufficient is False

    async def test_stops_when_all_retry_queries_were_already_searched(
        self, orchestrator, evaluator, searcher
    ):
        evaluator.evaluate.return_value = evaluation(sufficient=False, retry_queries=["sub1", "Q"])

        ctx = await orchestrator.retrieve("q", ["p"])

        evaluator.evaluate.assert_awaited_once()
        assert searcher.search.await_count == 3
        assert ctx.iteration == 1

    async def test_stops_when_retry_round_finds_no_new_unique_chunks(
        self, orchestrator, evaluator, searcher
    ):
        searcher.search = AsyncMock(return_value=[result("same")])
        always_insufficient_with_fresh_retries(evaluator)

        ctx = await orchestrator.retrieve("q", ["p"])

        assert evaluator.evaluate.await_count == 2
        assert ctx.iteration == 2
        assert ctx.iterations[1].new_unique_count == 0

    async def test_stops_at_max_iterations(self, planner, evaluator, searcher):
        o = AgenticOrchestrator(planner, evaluator, searcher, max_iterations=3)
        always_insufficient_with_fresh_retries(evaluator)

        ctx = await o.retrieve("q", ["p"])

        assert evaluator.evaluate.await_count == 3
        assert ctx.iteration == 3
        assert len(ctx.iterations) == 3

    async def test_default_max_iterations_is_four(self, orchestrator, evaluator):
        always_insufficient_with_fresh_retries(evaluator)

        ctx = await orchestrator.retrieve("q", ["p"])

        assert evaluator.evaluate.await_count == 4
        assert ctx.iteration == 4

    async def test_max_iterations_one_never_retries(self, planner, evaluator, searcher):
        o = AgenticOrchestrator(planner, evaluator, searcher, max_iterations=1)
        evaluator.evaluate.return_value = evaluation(sufficient=False, retry_queries=["again"])

        ctx = await o.retrieve("q", ["p"])

        evaluator.evaluate.assert_awaited_once()
        assert searched_queries(searcher) == ["q", "sub1", "sub2"]
        assert ctx.iteration == 1

    async def test_sufficient_wins_over_retry_queries(self, orchestrator, evaluator):
        evaluator.evaluate.return_value = evaluation(sufficient=True, retry_queries=["ignored"])

        ctx = await orchestrator.retrieve("q", ["p"])

        evaluator.evaluate.assert_awaited_once()
        assert len(ctx.iterations) == 1


class TestEmptyPlan:

    async def test_empty_plan_still_searches_original_query_and_evaluates(
        self, orchestrator, planner, evaluator, searcher
    ):
        planner.create.return_value = SearchPlan(subqueries=[])
        evaluator.evaluate.return_value = evaluation(sufficient=False)

        ctx = await orchestrator.retrieve("q", ["p"])

        assert searched_queries(searcher) == ["q"]
        assert [e.chunk_id for e in evaluator.evaluate.await_args.args[1]] == ["q-chunk"]
        assert [e.chunk_id for e in ctx.evidence] == ["q-chunk"]


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
        assert len(ctx.raw_evidence) == 1


class TestEvaluatorRateLimitFallback:

    async def test_first_iteration_keeps_evidence_without_searching_original_again(
        self, orchestrator, evaluator, searcher
    ):
        evaluator.evaluate.side_effect = LLMRateLimitError("limit")

        ctx = await orchestrator.retrieve("original", ["p"])

        assert searched_queries(searcher) == ["original", "sub1", "sub2"]
        assert [e.query for e in ctx.evidence] == ["original", "sub1", "sub2"]

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

        assert [e.query for e in ctx.evidence] == ["original", "sub1", "sub2", "retry1"]
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
        rankings, searched = [], set()

        assert await orchestrator._search_subqueries([], "q", rankings, searched) == []

        searcher.search.assert_not_called()
        assert rankings == []
        assert searched == set()

    async def test_searches_sequentially_in_given_order(self, orchestrator, searcher):
        rankings, searched = [], set()

        evidence = await orchestrator._search_subqueries(["x", "y", "z"], "x", rankings, searched)

        assert searched_queries(searcher) == ["x", "y", "z"]
        assert [e.query for e in evidence] == ["x", "y", "z"]

    async def test_records_rankings_and_marks_original_query(self, orchestrator):
        rankings, searched = [], set()

        await orchestrator._search_subqueries(["Hello  World", "y"], "hello world", rankings, searched)

        assert [is_original for is_original, _ in rankings] == [True, False]
        assert [[e.chunk_id for e in hits] for _, hits in rankings] == [
            ["Hello  World-chunk"],
            ["y-chunk"],
        ]

    async def test_marks_queries_as_searched_in_normalised_form(self, orchestrator):
        rankings, searched = [], set()

        await orchestrator._search_subqueries(["Hello  WORLD"], "q", rankings, searched)

        assert searched == {"hello world"}


class TestFallbackToHybrid:

    async def test_without_existing_state(self, orchestrator, searcher):
        ctx = await orchestrator._fallback_to_hybrid("q")

        assert [e.query for e in ctx.evidence] == ["q"]
        assert ctx.original_query == "q"
        assert ctx.plan.subqueries == ["q"]
        assert ctx.evaluation is None
        assert ctx.iterations == []

    async def test_original_query_hits_are_anchored_before_existing_rankings(self, orchestrator):
        rankings, searched = [], set()
        await orchestrator._search_subqueries(["old"], "q", rankings, searched)

        ctx = await orchestrator._fallback_to_hybrid("q", rankings=rankings, searched=searched)

        assert [e.query for e in ctx.evidence] == ["q", "old"]

    async def test_does_not_search_again_if_original_already_searched(self, orchestrator, searcher):
        rankings, searched = [], set()
        raw = await orchestrator._search_subqueries(["q"], "q", rankings, searched)
        searcher.search.reset_mock()

        ctx = await orchestrator._fallback_to_hybrid(
            "q", rankings=rankings, searched=searched, raw_evidence=raw
        )

        searcher.search.assert_not_called()
        assert [e.chunk_id for e in ctx.evidence] == ["q-chunk"]
        assert len(ctx.raw_evidence) == 1

    async def test_raw_evidence_includes_existing_and_new_hits(self, orchestrator):
        rankings, searched = [], set()
        raw = await orchestrator._search_subqueries(["old"], "q", rankings, searched)

        ctx = await orchestrator._fallback_to_hybrid(
            "q", rankings=rankings, searched=searched, raw_evidence=raw
        )

        assert [e.query for e in ctx.raw_evidence] == ["old", "q"]

    async def test_does_not_mutate_inputs(self, orchestrator):
        rankings, searched = [], set()
        raw = await orchestrator._search_subqueries(["old"], "q", rankings, searched)

        await orchestrator._fallback_to_hybrid(
            "q", rankings=rankings, searched=searched, raw_evidence=raw
        )

        assert len(rankings) == 1
        assert searched == {"old"}
        assert len(raw) == 1