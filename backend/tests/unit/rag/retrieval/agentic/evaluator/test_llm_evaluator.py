from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.retrieval.agentic.evaluator.llm_evaluator import LLMEvaluator
from src.rag.retrieval.agentic.exceptions import (
    LLMClientError,
    LLMParseError,
    LLMRateLimitError,
)
from src.rag.retrieval.agentic.models import RetrievalEvaluation, RetrievalEvidence
from src.rag.retrieval.agentic.prompts import EVALUATOR_SYSTEM


def ev(chunk_id="1", score=0.5, text=None, query="q"):
    return RetrievalEvidence(
        query=query, chunk_id=chunk_id, score=score,
        text=text if text is not None else f"text-{chunk_id}",
    )


def llm_response(**overrides):
    data = {
        "sufficient": True,
        "coverage": 0.9,
        "confidence": 0.8,
        "redundancy": 0.1,
        "missing_topics": [],
        "retry_queries": [],
    }
    data.update(overrides)
    return data


@pytest.fixture
def llm_client():
    client = MagicMock()
    client.complete_json = AsyncMock(return_value=llm_response())
    return client


@pytest.fixture
def evaluator(llm_client):
    return LLMEvaluator(llm_client=llm_client)


def assert_fallback(result):
    assert isinstance(result, RetrievalEvaluation)
    assert result.sufficient is False
    assert result.coverage == 0.0
    assert result.confidence == 0.0
    assert result.redundancy == 0.0
    assert result.missing_topics == []
    assert result.retry_queries == []


class TestInit:

    def test_defaults(self, llm_client):
        e = LLMEvaluator(llm_client=llm_client)
        assert e.llm_client is llm_client
        assert e.evidence_count == 5
        assert e.max_chars == 600

    def test_custom_values(self, llm_client):
        e = LLMEvaluator(llm_client=llm_client, evidence_count=2, max_chars=50)
        assert (e.evidence_count, e.max_chars) == (2, 50)


class TestFormatEvidence:

    def test_sorts_by_score_descending(self, evaluator):
        text, _ = evaluator._format_evidence(
            [ev("a", 0.1), ev("b", 0.9), ev("c", 0.5)], count=3, max_chars=100
        )
        assert text.index("text-b") < text.index("text-c") < text.index("text-a")

    def test_limits_to_count_and_returns_selected_count(self, evaluator):
        text, n = evaluator._format_evidence(
            [ev(str(i), i / 10) for i in range(6)], count=2, max_chars=100
        )
        assert n == 2
        assert "text-5" in text and "text-4" in text
        assert "text-3" not in text

    def test_count_larger_than_evidence(self, evaluator):
        _, n = evaluator._format_evidence([ev("a")], count=5, max_chars=100)
        assert n == 1

    def test_truncates_long_text_with_ellipsis(self, evaluator):
        text, _ = evaluator._format_evidence([ev("a", text="x" * 50)], count=1, max_chars=10)
        assert "x" * 10 + "..." in text
        assert "x" * 11 not in text

    def test_text_exactly_max_chars_not_truncated(self, evaluator):
        text, _ = evaluator._format_evidence([ev("a", text="x" * 10)], count=1, max_chars=10)
        assert "..." not in text

    def test_line_format_includes_index_and_score(self, evaluator):
        text, _ = evaluator._format_evidence([ev("a", 0.9, text="hello")], count=1, max_chars=100)
        assert text == "Evidence 1 (score: 0.9): hello"

    def test_blocks_separated_by_blank_line(self, evaluator):
        text, _ = evaluator._format_evidence(
            [ev("a", 0.9, text="A"), ev("b", 0.5, text="B")], count=2, max_chars=100
        )
        assert text == "Evidence 1 (score: 0.9): A\n\nEvidence 2 (score: 0.5): B"

    def test_empty_evidence(self, evaluator):
        assert evaluator._format_evidence([], count=5, max_chars=100) == ("", 0)

    def test_does_not_mutate_input_order(self, evaluator):
        evidences = [ev("a", 0.1), ev("b", 0.9)]
        evaluator._format_evidence(evidences, count=2, max_chars=100)
        assert [e.chunk_id for e in evidences] == ["a", "b"]


class TestEvaluate:

    async def test_maps_llm_response_to_evaluation(self, evaluator, llm_client):
        llm_client.complete_json.return_value = llm_response(
            sufficient=False, coverage=0.5, confidence=0.7, redundancy=0.2,
            missing_topics=["rate limiting"], retry_queries=["rate limit impl"],
        )

        result = await evaluator.evaluate("q", [ev()])

        assert result.sufficient is False
        assert result.coverage == 0.5
        assert result.confidence == 0.7
        assert result.redundancy == 0.2
        assert result.missing_topics == ["rate limiting"]
        assert result.retry_queries == ["rate limit impl"]

    async def test_prompt_contains_query_and_evidence(self, evaluator, llm_client):
        await evaluator.evaluate("my question", [ev("a", 0.9, text="useful chunk")])

        prompt = llm_client.complete_json.call_args.kwargs["prompt"]
        assert "my question" in prompt
        assert "useful chunk" in prompt
        assert "(1 chunks)" in prompt

    async def test_uses_evaluator_system_prompt(self, evaluator, llm_client):
        await evaluator.evaluate("q", [ev()])

        assert llm_client.complete_json.call_args.kwargs["system"] == EVALUATOR_SYSTEM

    async def test_default_limits_prompt_to_five_chunks(self, evaluator, llm_client):
        await evaluator.evaluate("q", [ev(str(i), i / 10) for i in range(8)])

        prompt = llm_client.complete_json.call_args.kwargs["prompt"]
        assert "(5 chunks)" in prompt

    async def test_custom_evidence_count_and_max_chars_are_used(self, llm_client):
        e = LLMEvaluator(llm_client=llm_client, evidence_count=1, max_chars=5)

        await e.evaluate("q", [ev("a", 0.9, text="abcdefghij"), ev("b", 0.1, text="zzz")])

        prompt = llm_client.complete_json.call_args.kwargs["prompt"]
        assert "(1 chunks)" in prompt
        assert "abcde..." in prompt
        assert "zzz" not in prompt

    async def test_empty_evidence_still_queries_llm_with_zero_chunks(self, evaluator, llm_client):
        await evaluator.evaluate("q", [])

        llm_client.complete_json.assert_awaited_once()
        assert "(0 chunks)" in llm_client.complete_json.call_args.kwargs["prompt"]

    async def test_query_with_braces_does_not_break_prompt(self, evaluator):
        result = await evaluator.evaluate("what is {x}?", [ev(text="has {braces}")])

        assert result.sufficient is True


class TestFallback:

    async def test_parse_error_returns_fallback(self, evaluator, llm_client):
        llm_client.complete_json.side_effect = LLMParseError("bad")

        assert_fallback(await evaluator.evaluate("q", [ev()]))

    @pytest.mark.parametrize(
        "missing_key",
        ["sufficient", "coverage", "confidence", "redundancy", "missing_topics", "retry_queries"],
    )
    async def test_missing_key_returns_fallback(self, evaluator, llm_client, missing_key):
        response = llm_response()
        del response[missing_key]
        llm_client.complete_json.return_value = response

        assert_fallback(await evaluator.evaluate("q", [ev()]))

    @pytest.mark.parametrize("field", ["coverage", "confidence", "redundancy"])
    async def test_out_of_range_value_returns_fallback(self, evaluator, llm_client, field):
        llm_client.complete_json.return_value = llm_response(**{field: 1.5})

        assert_fallback(await evaluator.evaluate("q", [ev()]))

    async def test_invalid_type_returns_fallback(self, evaluator, llm_client):
        llm_client.complete_json.return_value = llm_response(missing_topics="not a list")

        assert_fallback(await evaluator.evaluate("q", [ev()]))


class TestErrorPropagation:

    async def test_rate_limit_error_propagates_for_orchestrator_fallback(
        self, evaluator, llm_client
    ):
        llm_client.complete_json.side_effect = LLMRateLimitError("limit")

        with pytest.raises(LLMRateLimitError):
            await evaluator.evaluate("q", [ev()])

    async def test_client_error_propagates(self, evaluator, llm_client):
        llm_client.complete_json.side_effect = LLMClientError("down")

        with pytest.raises(LLMClientError):
            await evaluator.evaluate("q", [ev()])