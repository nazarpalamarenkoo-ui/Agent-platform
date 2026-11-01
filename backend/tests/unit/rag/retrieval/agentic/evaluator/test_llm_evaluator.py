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


def prompt_of(llm_client):
    return llm_client.complete_json.call_args.kwargs["prompt"]


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
        assert e.evidence_count == 8
        assert e.max_chars == 1500

    def test_custom_values(self, llm_client):
        e = LLMEvaluator(llm_client=llm_client, evidence_count=2, max_chars=50)
        assert (e.evidence_count, e.max_chars) == (2, 50)


class TestFormatEvidence:

    def test_keeps_given_order_and_does_not_sort_by_score(self, evaluator):
        text, _ = evaluator._format_evidence(
            [ev("a", 0.1), ev("b", 0.9), ev("c", 0.5)], count=3, max_chars=100
        )
        assert text.index("text-a") < text.index("text-b") < text.index("text-c")

    def test_limits_to_first_count_items_and_returns_selected_count(self, evaluator):
        text, n = evaluator._format_evidence(
            [ev(str(i), i / 10) for i in range(6)], count=2, max_chars=100
        )
        assert n == 2
        assert "text-0" in text and "text-1" in text
        assert "text-2" not in text

    def test_count_larger_than_evidence(self, evaluator):
        _, n = evaluator._format_evidence([ev("a")], count=5, max_chars=100)
        assert n == 1

    def test_duplicate_chunk_ids_are_skipped(self, evaluator):
        text, n = evaluator._format_evidence(
            [ev("a", text="first"), ev("a", text="dup"), ev("b", text="second")],
            count=5, max_chars=100,
        )
        assert n == 2
        assert "dup" not in text
        assert text == "Evidence 1: first\n\nEvidence 2: second"

    def test_duplicates_do_not_use_up_the_count(self, evaluator):
        text, n = evaluator._format_evidence(
            [ev("a"), ev("a"), ev("b")], count=2, max_chars=100
        )
        assert n == 2
        assert "text-b" in text

    def test_truncates_long_text_with_ellipsis(self, evaluator):
        text, _ = evaluator._format_evidence([ev("a", text="x" * 50)], count=1, max_chars=10)
        assert "x" * 10 + "..." in text
        assert "x" * 11 not in text

    def test_text_exactly_max_chars_not_truncated(self, evaluator):
        text, _ = evaluator._format_evidence([ev("a", text="x" * 10)], count=1, max_chars=10)
        assert "..." not in text

    def test_line_format_has_index_and_no_score(self, evaluator):
        text, _ = evaluator._format_evidence([ev("a", 0.9, text="hello")], count=1, max_chars=100)
        assert text == "Evidence 1: hello"
        assert "score" not in text

    def test_blocks_separated_by_blank_line(self, evaluator):
        text, _ = evaluator._format_evidence(
            [ev("a", 0.9, text="A"), ev("b", 0.5, text="B")], count=2, max_chars=100
        )
        assert text == "Evidence 1: A\n\nEvidence 2: B"

    def test_empty_evidence(self, evaluator):
        assert evaluator._format_evidence([], count=5, max_chars=100) == ("", 0)

    def test_does_not_mutate_input(self, evaluator):
        evidences = [ev("a", 0.1), ev("b", 0.9), ev("a", 0.3)]
        evaluator._format_evidence(evidences, count=3, max_chars=100)
        assert [e.chunk_id for e in evidences] == ["a", "b", "a"]


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

        prompt = prompt_of(llm_client)
        assert "my question" in prompt
        assert "useful chunk" in prompt
        assert "Top 1 retrieved chunks" in prompt

    async def test_prompt_does_not_show_scores(self, evaluator, llm_client):
        await evaluator.evaluate("q", [ev("a", 0.0123, text="chunk")])

        assert "0.0123" not in prompt_of(llm_client)

    async def test_uses_evaluator_system_prompt(self, evaluator, llm_client):
        await evaluator.evaluate("q", [ev()])

        assert llm_client.complete_json.call_args.kwargs["system"] == EVALUATOR_SYSTEM

    async def test_default_limits_prompt_to_eight_chunks(self, evaluator, llm_client):
        await evaluator.evaluate("q", [ev(str(i), i / 10) for i in range(10)])

        prompt = prompt_of(llm_client)
        assert "Top 8 retrieved chunks" in prompt
        assert "text-7" in prompt
        assert "text-8" not in prompt

    async def test_custom_evidence_count_and_max_chars_are_used(self, llm_client):
        e = LLMEvaluator(llm_client=llm_client, evidence_count=1, max_chars=5)

        await e.evaluate("q", [ev("a", 0.9, text="abcdefghij"), ev("b", 0.1, text="zzz")])

        prompt = prompt_of(llm_client)
        assert "Top 1 retrieved chunks" in prompt
        assert "abcde..." in prompt
        assert "zzz" not in prompt

    async def test_empty_evidence_still_queries_llm_with_zero_chunks(self, evaluator, llm_client):
        await evaluator.evaluate("q", [])

        llm_client.complete_json.assert_awaited_once()
        assert "Top 0 retrieved chunks" in prompt_of(llm_client)

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