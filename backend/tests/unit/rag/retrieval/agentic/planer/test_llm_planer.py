from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.retrieval.agentic.exceptions import (
    LLMClientError,
    LLMParseError,
    LLMRateLimitError,
)
from src.rag.retrieval.agentic.models import SearchPlan
from src.rag.retrieval.agentic.planner.llm_planner import LLMPlanner
from src.rag.retrieval.agentic.prompts import PLANNER_SYSTEM


@pytest.fixture
def llm_client():
    client = MagicMock()
    client.complete_json = AsyncMock(
        return_value={"subqueries": ["a", "b"], "reasoning": "split"}
    )
    return client


@pytest.fixture
def planner(llm_client):
    return LLMPlanner(llm_client=llm_client)


class TestInit:

    def test_stores_llm_client(self, llm_client):
        assert LLMPlanner(llm_client=llm_client).llm_client is llm_client


class TestCreate:

    async def test_returns_search_plan_from_llm_response(self, planner):
        plan = await planner.create("my query", ["python"])

        assert isinstance(plan, SearchPlan)
        assert plan.subqueries == ["a", "b"]
        assert plan.reasoning == "split"

    async def test_prompt_contains_query_and_joined_knowledge_packs(self, planner, llm_client):
        await planner.create("how to deploy", ["python", "docker"])

        prompt = llm_client.complete_json.call_args.kwargs["prompt"]
        assert "how to deploy" in prompt
        assert "python, docker" in prompt

    async def test_uses_planner_system_prompt(self, planner, llm_client):
        await planner.create("q", ["p"])

        assert llm_client.complete_json.call_args.kwargs["system"] == PLANNER_SYSTEM

    async def test_empty_knowledge_packs_still_works(self, planner, llm_client):
        plan = await planner.create("q", [])

        llm_client.complete_json.assert_awaited_once()
        assert plan.subqueries == ["a", "b"]

    async def test_query_with_braces_does_not_break_prompt(self, planner):
        plan = await planner.create("what is {x} in f-strings?", ["python"])

        assert plan.subqueries == ["a", "b"]

    async def test_missing_reasoning_defaults_to_empty(self, planner, llm_client):
        llm_client.complete_json.return_value = {"subqueries": ["a"]}

        plan = await planner.create("q", ["p"])

        assert plan.reasoning == ""

    async def test_more_than_five_subqueries_are_truncated(self, planner, llm_client):
        llm_client.complete_json.return_value = {"subqueries": [str(i) for i in range(8)]}

        plan = await planner.create("q", ["p"])

        assert plan.subqueries == ["0", "1", "2", "3", "4"]


class TestFallback:

    async def test_parse_error_falls_back_to_original_query(self, planner, llm_client):
        llm_client.complete_json.side_effect = LLMParseError("bad json")

        plan = await planner.create("original", ["p"])

        assert plan.subqueries == ["original"]

    async def test_missing_subqueries_key_falls_back(self, planner, llm_client):
        llm_client.complete_json.return_value = {"reasoning": "no subqueries here"}

        plan = await planner.create("original", ["p"])

        assert plan.subqueries == ["original"]

    async def test_invalid_subqueries_type_falls_back(self, planner, llm_client):
        llm_client.complete_json.return_value = {"subqueries": "not a list"}

        plan = await planner.create("original", ["p"])

        assert plan.subqueries == ["original"]

    async def test_non_string_items_in_subqueries_fall_back(self, planner, llm_client):
        llm_client.complete_json.return_value = {"subqueries": [{"x": 1}]}

        plan = await planner.create("original", ["p"])

        assert plan.subqueries == ["original"]


class TestErrorPropagation:

    async def test_rate_limit_error_propagates_for_orchestrator_fallback(
        self, planner, llm_client
    ):
        llm_client.complete_json.side_effect = LLMRateLimitError("limit")

        with pytest.raises(LLMRateLimitError):
            await planner.create("q", ["p"])

    async def test_client_error_propagates(self, planner, llm_client):
        llm_client.complete_json.side_effect = LLMClientError("api down")

        with pytest.raises(LLMClientError):
            await planner.create("q", ["p"])