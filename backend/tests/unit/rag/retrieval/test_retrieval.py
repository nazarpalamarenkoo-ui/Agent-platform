from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.retrieval.agentic.context_builder import ContextBuilder
from src.rag.retrieval.agentic.exceptions import LLMClientError
from src.rag.retrieval.agentic.models import (
    AgenticContext,
    IterationRecord,
    RetrievalEvaluation,
    RetrievalEvidence,
    SearchPlan,
)
from src.rag.retrieval.retrieval import Retrieval
from src.rag.storage.base_vector_store import VectorSearchResult


def make_result(id_, score=0.0):
    return VectorSearchResult(id=id_, score=score, payload={"text": id_})


def make_evidence(chunk_id, score=0.5, query="q", text=None):
    return RetrievalEvidence(
        query=query,
        chunk_id=chunk_id,
        score=score,
        text=text if text is not None else f"text {chunk_id}",
    )


def make_evaluation(sufficient=True):
    return RetrievalEvaluation(
        sufficient=sufficient,
        coverage=1.0,
        confidence=0.9,
        redundancy=0.0,
    )


def make_context(evidence=None, iteration=1, with_iterations=True):
    evaluation = make_evaluation()
    iterations = (
        [
            IterationRecord(
                iteration=1,
                subqueries=["sub1", "sub2"],
                new_evidence_count=len(evidence or []),
                total_evidence_count=len(evidence or []),
                evaluation=evaluation,
            )
        ]
        if with_iterations
        else []
    )
    return AgenticContext(
        original_query="original",
        plan=SearchPlan(subqueries=["sub1", "sub2"], reasoning="because"),
        evidence=evidence or [],
        evaluation=evaluation,
        iteration=iteration,
        iterations=iterations,
    )


@pytest.fixture
def mock_hybrid():
    hybrid = MagicMock()
    hybrid.retrieve = AsyncMock(return_value=[])
    return hybrid


@pytest.fixture
def mock_agentic():
    agentic = MagicMock()
    agentic.retrieve = AsyncMock(return_value=make_context())
    return agentic


@pytest.fixture
def mock_context_builder():
    builder = MagicMock()
    builder.build_evidence_list = MagicMock(return_value=[])
    return builder


@pytest.fixture
def retrieval(mock_hybrid, mock_agentic, mock_context_builder):
    return Retrieval(
        hybrid=mock_hybrid,
        agentic=mock_agentic,
        context_builder=mock_context_builder,
    )


class TestRetrievalInit:

    def test_stores_dependencies(self, mock_hybrid, mock_agentic, mock_context_builder):
        r = Retrieval(
            hybrid=mock_hybrid,
            agentic=mock_agentic,
            context_builder=mock_context_builder,
        )

        assert r.hybrid is mock_hybrid
        assert r.agentic is mock_agentic
        assert r.context_builder is mock_context_builder


class TestRetrieveHybrid:

    @pytest.mark.asyncio
    async def test_delegates_to_hybrid_retrieve(self, retrieval, mock_hybrid):
        await retrieval.retrieve_hybrid("my query", limit=10, top_n=3)

        mock_hybrid.retrieve.assert_awaited_once_with(
            query="my query", limit=10, top_n=3, k=60, filters=None
        )

    @pytest.mark.asyncio
    async def test_returns_hybrid_results_unchanged(self, retrieval, mock_hybrid):
        expected = [make_result("a", 0.9), make_result("b", 0.5)]
        mock_hybrid.retrieve.return_value = expected

        result = await retrieval.retrieve_hybrid("q", limit=10, top_n=2)

        assert result is expected

    @pytest.mark.asyncio
    async def test_default_k_is_sixty(self, retrieval, mock_hybrid):
        await retrieval.retrieve_hybrid("q", limit=10, top_n=3)

        assert mock_hybrid.retrieve.call_args.kwargs["k"] == 60

    @pytest.mark.asyncio
    async def test_custom_k_is_propagated(self, retrieval, mock_hybrid):
        await retrieval.retrieve_hybrid("q", limit=10, top_n=3, k=25)

        assert mock_hybrid.retrieve.call_args.kwargs["k"] == 25

    @pytest.mark.asyncio
    async def test_filters_default_to_none(self, retrieval, mock_hybrid):
        await retrieval.retrieve_hybrid("q", limit=10, top_n=3)

        assert mock_hybrid.retrieve.call_args.kwargs["filters"] is None

    @pytest.mark.asyncio
    async def test_passes_filters_through(self, retrieval, mock_hybrid):
        filters = SearchFilter(language="en", domains=["engineering"])

        await retrieval.retrieve_hybrid("q", limit=10, top_n=3, filters=filters)

        assert mock_hybrid.retrieve.call_args.kwargs["filters"] is filters

    @pytest.mark.asyncio
    async def test_propagates_limit_and_top_n(self, retrieval, mock_hybrid):
        await retrieval.retrieve_hybrid("q", limit=99, top_n=7)

        kwargs = mock_hybrid.retrieve.call_args.kwargs
        assert kwargs["limit"] == 99
        assert kwargs["top_n"] == 7

    @pytest.mark.asyncio
    async def test_empty_results_returned_as_empty_list(self, retrieval, mock_hybrid):
        mock_hybrid.retrieve.return_value = []

        result = await retrieval.retrieve_hybrid("q", limit=10, top_n=3)

        assert result == []

    @pytest.mark.asyncio
    async def test_does_not_touch_agentic_or_context_builder(
        self, retrieval, mock_agentic, mock_context_builder
    ):
        await retrieval.retrieve_hybrid("q", limit=10, top_n=3)

        mock_agentic.retrieve.assert_not_called()
        mock_context_builder.build_evidence_list.assert_not_called()

    @pytest.mark.asyncio
    async def test_propagates_hybrid_exceptions(self, retrieval, mock_hybrid):
        mock_hybrid.retrieve.side_effect = RuntimeError("qdrant down")

        with pytest.raises(RuntimeError, match="qdrant down"):
            await retrieval.retrieve_hybrid("q", limit=10, top_n=3)


class TestRetrieveAgentic:

    @pytest.mark.asyncio
    async def test_delegates_to_agentic_retrieve(self, retrieval, mock_agentic):
        await retrieval.retrieve_agentic("my query", knowledge_packs=["python", "rag"])

        mock_agentic.retrieve.assert_awaited_once_with(
            query="my query", knowledge_packs=["python", "rag"]
        )

    @pytest.mark.asyncio
    async def test_cleans_raw_evidence_via_context_builder(
        self, retrieval, mock_agentic, mock_context_builder
    ):
        raw_evidence = [make_evidence("a"), make_evidence("a"), make_evidence("b")]
        mock_agentic.retrieve.return_value = make_context(evidence=raw_evidence)

        await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        mock_context_builder.build_evidence_list.assert_called_once_with(raw_evidence)

    @pytest.mark.asyncio
    async def test_returned_context_uses_cleaned_evidence(
        self, retrieval, mock_agentic, mock_context_builder
    ):
        raw = [make_evidence("a"), make_evidence("a"), make_evidence("b")]
        cleaned = [make_evidence("b", score=0.9)]
        mock_agentic.retrieve.return_value = make_context(evidence=raw)
        mock_context_builder.build_evidence_list.return_value = cleaned

        result = await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        assert result.evidence == cleaned

    @pytest.mark.asyncio
    async def test_returns_agentic_context_instance(self, retrieval):
        result = await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        assert isinstance(result, AgenticContext)

    @pytest.mark.asyncio
    async def test_preserves_original_query_and_plan(
        self, retrieval, mock_agentic
    ):
        raw = make_context()
        mock_agentic.retrieve.return_value = raw

        result = await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        assert result.original_query == "original"
        assert result.plan == raw.plan
        assert result.plan.subqueries == ["sub1", "sub2"]

    @pytest.mark.asyncio
    async def test_preserves_evaluation_iteration_and_history(
        self, retrieval, mock_agentic
    ):
        raw = make_context(iteration=3)
        mock_agentic.retrieve.return_value = raw

        result = await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        assert result.evaluation == raw.evaluation
        assert result.iteration == 3
        assert result.iterations == raw.iterations
        assert len(result.iterations) == 1

    @pytest.mark.asyncio
    async def test_preserves_none_evaluation_for_hybrid_fallback(
        self, retrieval, mock_agentic
    ):
        raw = AgenticContext(
            original_query="q",
            plan=SearchPlan(subqueries=["q"]),
            evidence=[make_evidence("a")],
            evaluation=None,
            iteration=1,
            iterations=[],
        )
        mock_agentic.retrieve.return_value = raw

        result = await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        assert result.evaluation is None
        assert result.iterations == []

    @pytest.mark.asyncio
    async def test_returns_new_context_object(self, retrieval, mock_agentic):
        raw = make_context()
        mock_agentic.retrieve.return_value = raw

        result = await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        assert result is not raw

    @pytest.mark.asyncio
    async def test_does_not_mutate_raw_context_evidence(
        self, retrieval, mock_agentic, mock_context_builder
    ):
        raw_evidence = [make_evidence("a"), make_evidence("a"), make_evidence("b")]
        raw = make_context(evidence=raw_evidence)
        mock_agentic.retrieve.return_value = raw
        mock_context_builder.build_evidence_list.return_value = [make_evidence("b")]

        await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        assert len(raw.evidence) == 3

    @pytest.mark.asyncio
    async def test_empty_evidence_yields_empty_evidence(
        self, retrieval, mock_agentic, mock_context_builder
    ):
        mock_agentic.retrieve.return_value = make_context(evidence=[])
        mock_context_builder.build_evidence_list.return_value = []

        result = await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        mock_context_builder.build_evidence_list.assert_called_once_with([])
        assert result.evidence == []

    @pytest.mark.asyncio
    async def test_does_not_touch_hybrid(self, retrieval, mock_hybrid):
        await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        mock_hybrid.retrieve.assert_not_called()

    @pytest.mark.asyncio
    async def test_propagates_agentic_exceptions(self, retrieval, mock_agentic):
        mock_agentic.retrieve.side_effect = LLMClientError("boom")

        with pytest.raises(LLMClientError, match="boom"):
            await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

    @pytest.mark.asyncio
    async def test_context_builder_not_called_when_agentic_fails(
        self, retrieval, mock_agentic, mock_context_builder
    ):
        mock_agentic.retrieve.side_effect = LLMClientError("boom")

        with pytest.raises(LLMClientError):
            await retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        mock_context_builder.build_evidence_list.assert_not_called()

    @pytest.mark.asyncio
    async def test_propagates_context_builder_exceptions(
        self, retrieval, mock_context_builder
    ):
        mock_context_builder.build_evidence_list.side_effect = ValueError("bad evidence")

        with pytest.raises(ValueError, match="bad evidence"):
            await retrieval.retrieve_agentic("q", knowledge_packs=["p"])


class TestRetrieveAgenticWithRealContextBuilder:
    """Інтеграція Retrieval + реальний ContextBuilder (agentic замоканий)."""

    @pytest.fixture
    def real_retrieval(self, mock_hybrid, mock_agentic):
        return Retrieval(
            hybrid=mock_hybrid,
            agentic=mock_agentic,
            context_builder=ContextBuilder(max_chunks=3, max_chars=1000),
        )

    @pytest.mark.asyncio
    async def test_deduplicates_keeping_highest_score(
        self, real_retrieval, mock_agentic
    ):
        mock_agentic.retrieve.return_value = make_context(
            evidence=[
                make_evidence("a", score=0.3, query="q1"),
                make_evidence("a", score=0.8, query="q2"),
                make_evidence("b", score=0.5),
            ]
        )

        result = await real_retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        by_id = {e.chunk_id: e for e in result.evidence}
        assert set(by_id) == {"a", "b"}
        assert by_id["a"].score == 0.8
        assert by_id["a"].query == "q2"

    @pytest.mark.asyncio
    async def test_sorts_evidence_by_score_descending(
        self, real_retrieval, mock_agentic
    ):
        mock_agentic.retrieve.return_value = make_context(
            evidence=[
                make_evidence("low", score=0.1),
                make_evidence("high", score=0.9),
                make_evidence("mid", score=0.5),
            ]
        )

        result = await real_retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        assert [e.chunk_id for e in result.evidence] == ["high", "mid", "low"]

    @pytest.mark.asyncio
    async def test_truncates_to_max_chunks(self, real_retrieval, mock_agentic):
        mock_agentic.retrieve.return_value = make_context(
            evidence=[make_evidence(str(i), score=i / 10) for i in range(6)]
        )

        result = await real_retrieval.retrieve_agentic("q", knowledge_packs=["p"])

        assert len(result.evidence) == 3
        assert [e.chunk_id for e in result.evidence] == ["5", "4", "3"]

    @pytest.mark.asyncio
    async def test_truncates_by_max_chars(self, mock_hybrid, mock_agentic):
        r = Retrieval(
            hybrid=mock_hybrid,
            agentic=mock_agentic,
            context_builder=ContextBuilder(max_chunks=10, max_chars=15),
        )
        mock_agentic.retrieve.return_value = make_context(
            evidence=[
                make_evidence("a", score=0.9, text="x" * 10),
                make_evidence("b", score=0.5, text="y" * 10),
            ]
        )

        result = await r.retrieve_agentic("q", knowledge_packs=["p"])

        assert [e.chunk_id for e in result.evidence] == ["a"]