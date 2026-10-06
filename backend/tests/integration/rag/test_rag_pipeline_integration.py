import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import RateLimitError

from src.rag.embeddings.bge_m3 import EmbeddingResult
from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.retrieval.agentic.context_builder import ContextBuilder
from src.rag.retrieval.agentic.evaluator.heuristic_evaluator import HeuristicEvaluator
from src.rag.retrieval.agentic.evaluator.llm_evaluator import LLMEvaluator
from src.rag.retrieval.agentic.llm_client import LLMClient
from src.rag.retrieval.agentic.models import AgenticContext
from src.rag.retrieval.agentic.orchestrator import AgenticOrchestrator
from src.rag.retrieval.agentic.planner.heuristic_planner import HeuristicPlanner
from src.rag.retrieval.agentic.planner.llm_planner import LLMPlanner
from src.rag.retrieval.agentic.prompts import EVALUATOR_SYSTEM, PLANNER_SYSTEM
from src.rag.retrieval.agentic.search.hybrid_search_adapter import HybridSearchAdapter
from src.rag.retrieval.dense_search import DenseSearch
from src.rag.retrieval.hybrid_retrieval import HybridRetrieval
from src.rag.retrieval.query_encoder import QueryEncoder
from src.rag.retrieval.reranker import Reranker
from src.rag.retrieval.retrieval import Retrieval
from src.rag.retrieval.rrf import RRF
from src.rag.retrieval.sparse_search import SparseSearch
from src.rag.storage.base_vector_store import (
    DenseVector,
    SparseVector,
    VectorSearchResult,
)

pytestmark = pytest.mark.integration


QUERY = "how to set up jwt authentication and rate limiting"
SUB_AUTH = "jwt authentication setup"
SUB_RATE = "rate limiting api"
SUB_RETRY = "rate limiting redis"


def make_result(id_: str, score: float = 0.0, text: str = "some text") -> VectorSearchResult:
    return VectorSearchResult(id=id_, score=score, payload={"text": text})


def build_corpus() -> dict:
    return {
        SUB_AUTH: {
            "dense": [
                make_result("auth-1", text="jwt authentication setup guide"),
                make_result("shared", text="jwt rate limiting overview"),
            ],
            "sparse": [
                make_result("auth-1", text="jwt authentication setup guide"),
                make_result("auth-2", text="jwt token refresh"),
            ],
        },
        SUB_RATE: {
            "dense": [
                make_result("rate-1", text="rate limiting api middleware"),
                make_result("shared", text="jwt rate limiting overview"),
            ],
            "sparse": [make_result("rate-1", text="rate limiting api middleware")],
        },
        SUB_RETRY: {
            "dense": [make_result("redis-1", text="rate limiting redis cache")],
            "sparse": [],
        },
        QUERY: {
            "dense": [make_result("orig-1", text="jwt authentication rate limiting basics")],
            "sparse": [],
        },
    }


def evaluation_json(sufficient=True, retry_queries=None, **overrides) -> dict:
    data = {
        "sufficient": sufficient,
        "coverage": 1.0 if sufficient else 0.4,
        "confidence": 0.9 if sufficient else 0.4,
        "redundancy": 0.0,
        "missing_topics": [] if sufficient else ["rate limiting"],
        "retry_queries": retry_queries or [],
    }
    data.update(overrides)
    return data


def plan_json(*subqueries) -> dict:
    return {"subqueries": list(subqueries), "reasoning": "split by topic"}


def make_rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "http://test")
    return RateLimitError("limit", response=httpx.Response(429, request=request), body=None)


class FakeEmbedding:

    def __init__(self):
        self.vector_to_query: dict[int, str] = {}

    def embed(self, queries: list[str]) -> list[EmbeddingResult]:
        results = []
        for query in queries:
            idx = len(self.vector_to_query) + 1
            self.vector_to_query[idx] = query
            results.append(
                EmbeddingResult(
                    dense=DenseVector(values=[float(idx)]),
                    sparse=SparseVector(indices=[idx], values=[1.0]),
                )
            )
        return results


class FakeIndex:

    def __init__(self, embedding: FakeEmbedding, corpus: dict | None = None, default=None):
        self.embedding = embedding
        self.corpus = corpus or {}
        self.default = default
        self.vector_store = MagicMock()
        self.vector_store.search_dense = AsyncMock(side_effect=self._dense)
        self.vector_store.search_sparse = AsyncMock(side_effect=self._sparse)

    def _lookup(self, query: str, kind: str) -> list[VectorSearchResult]:
        if query in self.corpus:
            return list(self.corpus[query].get(kind, []))
        if self.default is not None and kind == "dense":
            return list(self.default(query))
        return []

    async def _dense(self, vector, limit, filters=None):
        query = self.embedding.vector_to_query[int(vector.values[0])]
        return self._lookup(query, "dense")[:limit]

    async def _sparse(self, vector, limit, filters=None):
        query = self.embedding.vector_to_query[int(vector.indices[0])]
        return self._lookup(query, "sparse")[:limit]


class OverlapRerankModel:

    def compute_score(self, pairs, normalize=True):
        scores = []
        for query, text in pairs:
            q_words = set(query.lower().split())
            t_words = set(text.lower().split())
            scores.append(len(q_words & t_words) / len(q_words) if q_words else 0.0)
        return scores


class FakeOpenAI:

    def __init__(self, plan, evaluations):
        self.plan = plan
        self.evaluations = list(evaluations)
        self.calls: list[tuple[str, str]] = []

    async def create(self, model, messages, max_tokens):
        system, user = messages[0]["content"], messages[-1]["content"]
        self.calls.append((system, user))

        if system == PLANNER_SYSTEM:
            item = self.plan
        elif system == EVALUATOR_SYSTEM:
            assert self.evaluations, "LLM evaluator called more times than scripted"
            item = self.evaluations.pop(0)
        else:
            raise AssertionError(f"unexpected system prompt: {system[:40]!r}")

        if isinstance(item, Exception):
            raise item
        content = item if isinstance(item, str) else json.dumps(item)
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    @property
    def planner_calls(self):
        return [c for c in self.calls if c[0] == PLANNER_SYSTEM]

    @property
    def evaluator_calls(self):
        return [c for c in self.calls if c[0] == EVALUATOR_SYSTEM]


@pytest.fixture
def embedding():
    return FakeEmbedding()


@pytest.fixture
def index(embedding):
    return FakeIndex(embedding, corpus=build_corpus())


@pytest.fixture
def patch_reranker_model(monkeypatch):
    monkeypatch.setattr(
        "src.rag.retrieval.reranker.FlagReranker",
        lambda *args, **kwargs: OverlapRerankModel(),
    )


@pytest.fixture
def make_llm(monkeypatch):

    def factory(plan=None, evaluations=(), max_retries=3):
        fake = FakeOpenAI(plan=plan, evaluations=evaluations)
        fake_sdk_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake.create))
        )
        monkeypatch.setattr(
            "src.rag.retrieval.agentic.llm_client.AsyncOpenAI",
            lambda **kwargs: fake_sdk_client,
        )
        client = LLMClient(api_key="test", max_retries=max_retries, retry_delay=0)
        return client, fake

    return factory


@pytest.fixture
def build_hybrid(patch_reranker_model, embedding):
    def factory(index, top_n=5):
        return HybridRetrieval(
            query_encoder=QueryEncoder(embedding=embedding),
            sparse_search=SparseSearch(vector_store=index.vector_store),
            dense_search=DenseSearch(vector_store=index.vector_store),
            rrf=RRF(),
            reranker=Reranker(top_n=top_n),
        )

    return factory


@pytest.fixture
def build_retrieval(build_hybrid):

    def factory(
        index,
        planner,
        evaluator,
        *,
        limit=20,
        top_n=5,
        k=60,
        filters=None,
        max_iterations=4,
        max_chunks=10,
    ) -> Retrieval:
        hybrid = build_hybrid(index, top_n=top_n)
        searcher = HybridSearchAdapter(
            hybrid_retrieval=hybrid, limit=limit, top_n=top_n, k=k, filters=filters
        )
        orchestrator = AgenticOrchestrator(
            planner=planner,
            evaluator=evaluator,
            searcher=searcher,
            max_iterations=max_iterations,
        )
        return Retrieval(
            hybrid=hybrid,
            agentic=orchestrator,
            context_builder=ContextBuilder(max_chunks=max_chunks),
        )

    return factory


def ids(context: AgenticContext) -> list[str]:
    return [e.chunk_id for e in context.evidence]


class TestRetrievalHybridMode:

    @pytest.fixture
    def retrieval(self, index, build_retrieval, make_llm):
        llm, _ = make_llm()
        return build_retrieval(index, LLMPlanner(llm), LLMEvaluator(llm))

    @pytest.mark.asyncio
    async def test_returns_results_ranked_by_reranker(self, retrieval):
        results = await retrieval.retrieve_hybrid(SUB_AUTH, limit=10, top_n=5)

        assert results[0].id == "auth-1"
        assert results[0].score == pytest.approx(1.0)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_fuses_dense_and_sparse_candidates_without_duplicates(self, retrieval):
        results = await retrieval.retrieve_hybrid(SUB_AUTH, limit=10, top_n=10)

        result_ids = [r.id for r in results]
        assert sorted(result_ids) == ["auth-1", "auth-2", "shared"]

    @pytest.mark.asyncio
    async def test_top_n_truncates_final_results(self, retrieval):
        results = await retrieval.retrieve_hybrid(SUB_AUTH, limit=10, top_n=2)

        assert len(results) == 2
        assert results[0].id == "auth-1"

    @pytest.mark.asyncio
    async def test_filters_reach_vector_store_for_dense_and_sparse(self, retrieval, index):
        filters = SearchFilter(language="en", domains=["engineering"])

        await retrieval.retrieve_hybrid(SUB_AUTH, limit=10, top_n=3, filters=filters)

        assert index.vector_store.search_dense.await_args.kwargs["filters"] is filters
        assert index.vector_store.search_sparse.await_args.kwargs["filters"] is filters

    @pytest.mark.asyncio
    async def test_limit_reaches_vector_store(self, retrieval, index):
        await retrieval.retrieve_hybrid(SUB_AUTH, limit=1, top_n=3)

        assert index.vector_store.search_dense.await_args.kwargs["limit"] == 1
        assert index.vector_store.search_sparse.await_args.kwargs["limit"] == 1

    @pytest.mark.asyncio
    async def test_unknown_query_returns_empty_list(self, retrieval):
        assert await retrieval.retrieve_hybrid("nothing matches", limit=10, top_n=3) == []

    @pytest.mark.asyncio
    async def test_hybrid_mode_does_not_call_llm(self, index, build_retrieval, make_llm):
        llm, fake = make_llm()
        retrieval = build_retrieval(index, LLMPlanner(llm), LLMEvaluator(llm))

        await retrieval.retrieve_hybrid(SUB_AUTH, limit=10, top_n=3)

        assert fake.calls == []


class TestAgenticPipelineWithLLM:

    @pytest.fixture
    def run(self, index, build_retrieval, make_llm):

        async def _run(plan, evaluations, query=QUERY, **stack_kwargs):
            llm, fake = make_llm(plan=plan, evaluations=evaluations)
            retrieval = build_retrieval(
                index, LLMPlanner(llm), LLMEvaluator(llm), **stack_kwargs
            )
            context = await retrieval.retrieve_agentic(query, knowledge_packs=["backend"])
            return context, fake

        return _run


    @pytest.mark.asyncio
    async def test_single_iteration_when_evaluator_is_satisfied(self, run):
        context, fake = await run(
            plan_json(SUB_AUTH, SUB_RATE), [evaluation_json(sufficient=True)]
        )

        assert isinstance(context, AgenticContext)
        assert context.original_query == QUERY
        assert context.plan.subqueries == [SUB_AUTH, SUB_RATE]
        assert context.iteration == 1
        assert len(context.iterations) == 1
        assert context.evaluation.sufficient is True
        assert len(fake.planner_calls) == 1
        assert len(fake.evaluator_calls) == 1

    @pytest.mark.asyncio
    async def test_every_subquery_hits_dense_and_sparse_once(self, run, index):
        await run(plan_json(SUB_AUTH, SUB_RATE), [evaluation_json()])

        assert index.vector_store.search_dense.await_count == 2
        assert index.vector_store.search_sparse.await_count == 2

    @pytest.mark.asyncio
    async def test_final_evidence_is_deduplicated_and_sorted_by_rerank_score(self, run):
        context, _ = await run(plan_json(SUB_AUTH, SUB_RATE), [evaluation_json()])

        assert len(ids(context)) == len(set(ids(context)))
        assert set(ids(context)) == {"auth-1", "rate-1", "shared", "auth-2"}
        assert ids(context)[:2] == ["auth-1", "rate-1"]
        scores = [e.score for e in context.evidence]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_duplicate_chunk_keeps_best_score_and_its_subquery(self, run):
        context, _ = await run(plan_json(SUB_AUTH, SUB_RATE), [evaluation_json()])

        shared = next(e for e in context.evidence if e.chunk_id == "shared")
        assert shared.query == SUB_RATE
        assert shared.score == pytest.approx(2 / 3)

    @pytest.mark.asyncio
    async def test_evidence_text_and_metadata_come_from_vector_store_payload(self, run):
        context, _ = await run(plan_json(SUB_AUTH, SUB_RATE), [evaluation_json()])

        auth = next(e for e in context.evidence if e.chunk_id == "auth-1")
        assert auth.text == "jwt authentication setup guide"
        assert auth.metadata == {"text": "jwt authentication setup guide"}

    @pytest.mark.asyncio
    async def test_planner_prompt_contains_query_and_knowledge_packs(self, run):
        _, fake = await run(plan_json(SUB_AUTH), [evaluation_json()])

        _, user_prompt = fake.planner_calls[0]
        assert QUERY in user_prompt
        assert "backend" in user_prompt

    @pytest.mark.asyncio
    async def test_evaluator_sees_real_retrieved_chunks(self, run):
        _, fake = await run(plan_json(SUB_AUTH, SUB_RATE), [evaluation_json()])

        _, user_prompt = fake.evaluator_calls[0]
        assert QUERY in user_prompt
        assert "jwt authentication setup guide" in user_prompt
        assert "rate limiting api middleware" in user_prompt


    @pytest.mark.asyncio
    async def test_retry_queries_trigger_second_search_round(self, run, index):
        context, _ = await run(
            plan_json(SUB_AUTH, SUB_RATE),
            [
                evaluation_json(sufficient=False, retry_queries=[SUB_RETRY]),
                evaluation_json(sufficient=True),
            ],
        )

        assert context.iteration == 2
        assert [r.subqueries for r in context.iterations] == [
            [SUB_AUTH, SUB_RATE],
            [SUB_RETRY],
        ]
        assert "redis-1" in ids(context)
        assert index.vector_store.search_dense.await_count == 3

    @pytest.mark.asyncio
    async def test_second_evaluation_sees_evidence_from_both_rounds(self, run):
        _, fake = await run(
            plan_json(SUB_AUTH, SUB_RATE),
            [
                evaluation_json(sufficient=False, retry_queries=[SUB_RETRY]),
                evaluation_json(sufficient=True),
            ],
        )

        _, second_prompt = fake.evaluator_calls[1]
        assert "rate limiting redis cache" in second_prompt
        assert "jwt authentication setup guide" in second_prompt

    @pytest.mark.asyncio
    async def test_iteration_records_count_new_and_total_evidence(self, run):
        context, _ = await run(
            plan_json(SUB_AUTH, SUB_RATE),
            [
                evaluation_json(sufficient=False, retry_queries=[SUB_RETRY]),
                evaluation_json(sufficient=True),
            ],
        )

        first, second = context.iterations
        assert (first.new_evidence_count, first.total_evidence_count) == (5, 5)
        assert (second.new_evidence_count, second.total_evidence_count) == (1, 6)

    @pytest.mark.asyncio
    async def test_stops_when_insufficient_but_no_retry_queries(self, run):
        context, fake = await run(
            plan_json(SUB_AUTH, SUB_RATE),
            [evaluation_json(sufficient=False, retry_queries=[])],
        )

        assert context.iteration == 1
        assert context.evaluation.sufficient is False
        assert len(fake.evaluator_calls) == 1

    @pytest.mark.asyncio
    async def test_respects_max_iterations(self, run):
        context, fake = await run(
            plan_json(SUB_AUTH),
            [evaluation_json(sufficient=False, retry_queries=[SUB_RETRY])] * 2,
            max_iterations=2,
        )

        assert context.iteration == 2
        assert len(fake.evaluator_calls) == 2

    @pytest.mark.asyncio
    async def test_reretrieved_chunks_across_iterations_are_deduplicated(self, run):
        context, _ = await run(
            plan_json(SUB_AUTH),
            [
                evaluation_json(sufficient=False, retry_queries=[SUB_AUTH]),
                evaluation_json(sufficient=True),
            ],
        )

        assert len(ids(context)) == len(set(ids(context)))
        assert context.iterations[-1].total_evidence_count == 6 


    @pytest.mark.asyncio
    async def test_max_chunks_truncates_final_evidence(self, run):
        context, _ = await run(
            plan_json(SUB_AUTH, SUB_RATE), [evaluation_json()], max_chunks=2
        )

        assert ids(context) == ["auth-1", "rate-1"]


    @pytest.mark.asyncio
    async def test_adapter_filters_reach_vector_store_on_every_call(self, run, index):
        filters = SearchFilter(language="en", knowledge_packs=["backend"])

        await run(
            plan_json(SUB_AUTH, SUB_RATE),
            [
                evaluation_json(sufficient=False, retry_queries=[SUB_RETRY]),
                evaluation_json(sufficient=True),
            ],
            filters=filters,
        )

        calls = (
            index.vector_store.search_dense.await_args_list
            + index.vector_store.search_sparse.await_args_list
        )
        assert len(calls) == 6
        assert all(c.kwargs["filters"] is filters for c in calls)

    @pytest.mark.asyncio
    async def test_adapter_limit_reaches_vector_store(self, run, index):
        await run(plan_json(SUB_AUTH), [evaluation_json()], limit=7)

        assert index.vector_store.search_dense.await_args.kwargs["limit"] == 7
        assert index.vector_store.search_sparse.await_args.kwargs["limit"] == 7

    @pytest.mark.asyncio
    async def test_adapter_top_n_limits_results_per_subquery(self, run):
        context, _ = await run(
            plan_json(SUB_AUTH), [evaluation_json()], top_n=1
        )

        assert ids(context) == ["auth-1"]


    @pytest.mark.asyncio
    async def test_invalid_planner_json_falls_back_to_original_query(self, run, index):
        context, _ = await run("this is not json", [evaluation_json()])

        assert context.plan.subqueries == [QUERY]
        assert ids(context) == ["orig-1"]
        assert context.evaluation.sufficient is True

    @pytest.mark.asyncio
    async def test_planner_json_wrapped_in_markdown_fence_is_accepted(self, run):
        fenced = "```json\n" + json.dumps(plan_json(SUB_AUTH, SUB_RATE)) + "\n```"

        context, _ = await run(fenced, [evaluation_json()])

        assert context.plan.subqueries == [SUB_AUTH, SUB_RATE]

    @pytest.mark.asyncio
    async def test_planner_output_is_capped_at_five_subqueries(self, run, index):
        many = [f"topic {i}" for i in range(8)]

        context, _ = await run(plan_json(*many), [evaluation_json()])

        assert context.plan.subqueries == many[:5]
        assert index.vector_store.search_dense.await_count == 5

    @pytest.mark.asyncio
    async def test_invalid_evaluator_json_yields_fallback_evaluation_and_stops(self, run):
        context, fake = await run(plan_json(SUB_AUTH, SUB_RATE), ["definitely not json"])

        assert context.iteration == 1
        assert context.evaluation.sufficient is False
        assert context.evaluation.coverage == 0.0
        assert context.evaluation.retry_queries == []
        assert len(fake.evaluator_calls) == 1
        assert len(ids(context)) > 0  # evidence все одно повертається

    @pytest.mark.asyncio
    async def test_evaluator_json_with_missing_field_yields_fallback(self, run):
        broken = evaluation_json()
        del broken["retry_queries"]

        context, _ = await run(plan_json(SUB_AUTH), [broken])

        assert context.evaluation.sufficient is False
        assert context.evaluation.coverage == 0.0


    @pytest.mark.asyncio
    async def test_planner_rate_limit_degrades_to_plain_hybrid_search(self, run, index):
        context, fake = await run(make_rate_limit_error(), [])

        assert len(fake.planner_calls) == 3 
        assert fake.evaluator_calls == []
        assert context.plan.subqueries == [QUERY]
        assert context.evaluation is None
        assert context.iterations == []
        assert ids(context) == ["orig-1"]
        assert index.vector_store.search_dense.await_count == 1

    @pytest.mark.asyncio
    async def test_evaluator_rate_limit_keeps_evidence_and_adds_hybrid_fallback(self, run):
        context, fake = await run(
            plan_json(SUB_AUTH, SUB_RATE), [make_rate_limit_error()] * 3
        )

        assert len(fake.evaluator_calls) == 3
        assert context.evaluation is None
        assert context.iterations == []
        assert context.plan.subqueries == [QUERY]
        assert set(ids(context)) == {"auth-1", "rate-1", "shared", "auth-2", "orig-1"}

    @pytest.mark.asyncio
    async def test_evaluator_rate_limit_on_retry_round_keeps_earlier_evidence(self, run):
        context, _ = await run(
            plan_json(SUB_AUTH, SUB_RATE),
            [evaluation_json(sufficient=False, retry_queries=[SUB_RETRY])]
            + [make_rate_limit_error()] * 3,
        )

        assert {"auth-1", "rate-1", "redis-1", "orig-1"} <= set(ids(context))
        assert context.evaluation is None
        assert context.iterations == []

    @pytest.mark.asyncio
    async def test_transient_rate_limit_is_retried_transparently(self, run):
        context, fake = await run(
            plan_json(SUB_AUTH, SUB_RATE),
            [make_rate_limit_error(), evaluation_json(sufficient=True)],
        )

        assert len(fake.evaluator_calls) == 2
        assert context.evaluation.sufficient is True
        assert len(context.iterations) == 1

class TestAgenticPipelineHeuristic:

    @staticmethod
    def echo_index(embedding, text_for):
        return FakeIndex(
            embedding,
            default=lambda q: [make_result(f"chunk:{q}", text=text_for(q))],
        )

    @pytest.mark.asyncio
    async def test_relevant_results_are_sufficient_in_one_iteration(
        self, embedding, build_retrieval
    ):
        index = self.echo_index(embedding, text_for=lambda q: q)  # повний збіг -> score 1.0
        retrieval = build_retrieval(index, HeuristicPlanner(), HeuristicEvaluator())

        context = await retrieval.retrieve_agentic(QUERY, knowledge_packs=["backend"])

        assert context.plan.subqueries[0] == QUERY
        assert 1 <= len(context.plan.subqueries) <= 4
        assert context.iteration == 1
        assert context.evaluation.sufficient is True
        assert context.evaluation.coverage == 1.0
        assert context.evaluation.confidence == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_every_planned_subquery_is_searched_exactly_once(
        self, embedding, build_retrieval
    ):
        index = self.echo_index(embedding, text_for=lambda q: q)
        retrieval = build_retrieval(index, HeuristicPlanner(), HeuristicEvaluator())

        context = await retrieval.retrieve_agentic(QUERY, knowledge_packs=["backend"])

        searched = [
            embedding.vector_to_query[int(c.kwargs["vector"].values[0])]
            for c in index.vector_store.search_dense.await_args_list
        ]
        assert searched == context.plan.subqueries

    @pytest.mark.asyncio
    async def test_evidence_is_tagged_with_planned_subqueries(
        self, embedding, build_retrieval
    ):
        index = self.echo_index(embedding, text_for=lambda q: q)
        retrieval = build_retrieval(index, HeuristicPlanner(), HeuristicEvaluator())

        context = await retrieval.retrieve_agentic(QUERY, knowledge_packs=["backend"])

        assert {e.query for e in context.evidence} <= set(context.plan.subqueries)
        assert QUERY in {e.query for e in context.evidence}

    @pytest.mark.asyncio
    async def test_irrelevant_results_are_insufficient_and_not_retried(
        self, embedding, build_retrieval
    ):
        index = self.echo_index(embedding, text_for=lambda q: "completely unrelated words")
        retrieval = build_retrieval(index, HeuristicPlanner(), HeuristicEvaluator())

        context = await retrieval.retrieve_agentic(QUERY, knowledge_packs=["backend"])

        assert context.evaluation.sufficient is False
        assert context.evaluation.coverage == 0.0
        assert context.iteration == 1
        assert len(context.iterations) == 1
        assert len(context.evidence) > 0

    @pytest.mark.asyncio
    async def test_empty_index_yields_empty_evidence_and_zeroed_evaluation(
        self, embedding, build_retrieval
    ):
        index = FakeIndex(embedding)  # нічого не знаходить
        retrieval = build_retrieval(index, HeuristicPlanner(), HeuristicEvaluator())

        context = await retrieval.retrieve_agentic(QUERY, knowledge_packs=["backend"])

        assert context.evidence == []
        assert context.evaluation.sufficient is False
        assert context.evaluation.coverage == 0.0
        assert context.evaluation.confidence == 0.0
        assert context.iteration == 1

    @pytest.mark.asyncio
    async def test_filters_and_limits_reach_store_in_heuristic_mode(
        self, embedding, build_retrieval
    ):
        index = self.echo_index(embedding, text_for=lambda q: q)
        filters = SearchFilter(language="en")
        retrieval = build_retrieval(
            index, HeuristicPlanner(), HeuristicEvaluator(), limit=9, filters=filters
        )

        await retrieval.retrieve_agentic(QUERY, knowledge_packs=["backend"])

        for call in index.vector_store.search_dense.await_args_list:
            assert call.kwargs["limit"] == 9
            assert call.kwargs["filters"] is filters

    @pytest.mark.asyncio
    async def test_max_chunks_applies_in_heuristic_mode(self, embedding, build_retrieval):
        index = self.echo_index(embedding, text_for=lambda q: q)
        retrieval = build_retrieval(
            index, HeuristicPlanner(), HeuristicEvaluator(), max_chunks=1
        )

        context = await retrieval.retrieve_agentic(QUERY, knowledge_packs=["backend"])

        assert len(context.evidence) == 1

class TestHybridAndAgenticShareStack:

    @pytest.mark.asyncio
    async def test_agentic_search_equals_hybrid_search_for_single_subquery_plan(
        self, index, build_retrieval, make_llm
    ):
        llm, _ = make_llm(plan=plan_json(SUB_AUTH), evaluations=[evaluation_json()])
        retrieval = build_retrieval(index, LLMPlanner(llm), LLMEvaluator(llm))

        hybrid = await retrieval.retrieve_hybrid(SUB_AUTH, limit=20, top_n=5)
        agentic = await retrieval.retrieve_agentic(QUERY, knowledge_packs=["backend"])

        assert [r.id for r in hybrid] == ids(agentic)
        assert [r.score for r in hybrid] == pytest.approx([e.score for e in agentic.evidence])