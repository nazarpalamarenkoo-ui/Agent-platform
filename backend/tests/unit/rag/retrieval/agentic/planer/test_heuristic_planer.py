from unittest.mock import MagicMock, patch

import pytest

from src.rag.retrieval.agentic.models import SearchPlan
from src.rag.retrieval.agentic.planner.heuristic_planner import HeuristicPlanner

MODULE = "src.rag.retrieval.agentic.planner.heuristic_planner"


def patch_extractor(keywords):
    """keywords: list of str -> yake-like [(kw, score), ...]"""
    cls = MagicMock()
    cls.return_value.extract_keywords.return_value = [(kw, 0.1) for kw in keywords]
    return patch(f"{MODULE}.KeywordExtractor", cls), cls


class TestInit:

    def test_defaults(self):
        p = HeuristicPlanner()
        assert (p.top_n, p.language, p.n, p.max_len) == (5, "en", 3, 300)

    def test_custom_values(self):
        p = HeuristicPlanner(top_n=2, language="uk", n=1, max_len=50)
        assert (p.top_n, p.language, p.n, p.max_len) == (2, "uk", 1, 50)


class TestCreate:

    async def test_empty_query_returns_empty_plan_without_extracting(self):
        patcher, cls = patch_extractor(["x"])
        with patcher:
            plan = await HeuristicPlanner().create("", ["p"])

        assert isinstance(plan, SearchPlan)
        assert plan.subqueries == []
        cls.assert_not_called()

    async def test_first_subquery_is_original_query(self):
        patcher, _ = patch_extractor(["jwt auth", "fastapi"])
        with patcher:
            plan = await HeuristicPlanner().create("how to do jwt auth in fastapi", ["p"])

        assert plan.subqueries[0] == "how to do jwt auth in fastapi"

    async def test_appends_keywords_after_query(self):
        patcher, _ = patch_extractor(["jwt auth", "fastapi"])
        with patcher:
            plan = await HeuristicPlanner().create("original query", ["p"])

        assert plan.subqueries == ["original query", "jwt auth", "fastapi"]

    async def test_uses_at_most_three_keywords(self):
        patcher, _ = patch_extractor(["kw1", "kw2", "kw3", "kw4", "kw5"])
        with patcher:
            plan = await HeuristicPlanner().create("original query", ["p"])

        assert plan.subqueries == ["original query", "kw1", "kw2", "kw3"]
        assert len(plan.subqueries) <= 4

    async def test_skips_keyword_equal_to_query_case_insensitive(self):
        patcher, _ = patch_extractor(["ORIGINAL QUERY", "other"])
        with patcher:
            plan = await HeuristicPlanner().create("original query", ["p"])

        assert plan.subqueries == ["original query", "other"]

    async def test_skips_duplicate_keywords(self):
        patcher, _ = patch_extractor(["same", "same", "diff"])
        with patcher:
            plan = await HeuristicPlanner().create("original query", ["p"])

        assert plan.subqueries == ["original query", "same", "diff"]

    async def test_filters_too_short_keywords(self):
        patcher, _ = patch_extractor(["ab", "x", "good kw"])
        with patcher:
            plan = await HeuristicPlanner().create("original query", ["p"])

        assert plan.subqueries == ["original query", "good kw"]

    async def test_three_char_keyword_is_kept(self):
        patcher, _ = patch_extractor(["abc"])
        with patcher:
            plan = await HeuristicPlanner().create("original query", ["p"])

        assert "abc" in plan.subqueries

    async def test_filters_too_long_keywords(self):
        patcher, _ = patch_extractor(["k" * 20, "ok kw"])
        with patcher:
            plan = await HeuristicPlanner(max_len=20).create("original query", ["p"])

        assert plan.subqueries == ["original query", "ok kw"]

    async def test_no_keywords_returns_only_query(self):
        patcher, _ = patch_extractor([])
        with patcher:
            plan = await HeuristicPlanner().create("original query", ["p"])

        assert plan.subqueries == ["original query"]

    async def test_constructs_extractor_with_configured_params(self):
        patcher, cls = patch_extractor([])
        with patcher:
            await HeuristicPlanner(top_n=7, language="uk", n=2).create("query", ["p"])

        cls.assert_called_once_with(lan="uk", n=2, top=7)

    async def test_extracts_keywords_from_query(self):
        patcher, cls = patch_extractor([])
        with patcher:
            await HeuristicPlanner().create("some query", ["p"])

        cls.return_value.extract_keywords.assert_called_once_with("some query")

    async def test_ignores_knowledge_packs(self):
        patcher, _ = patch_extractor(["kw one"])
        with patcher:
            a = await HeuristicPlanner().create("query", ["x"])
            b = await HeuristicPlanner().create("query", [])

        assert a.subqueries == b.subqueries


class TestCreateWithRealYake:

    async def test_real_extractor_smoke(self):
        query = "How to configure JWT authentication and rate limiting in FastAPI"

        plan = await HeuristicPlanner().create(query, ["python"])

        assert plan.subqueries[0] == query
        assert 1 <= len(plan.subqueries) <= 4
        assert len(set(plan.subqueries)) == len(plan.subqueries)