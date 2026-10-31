import asyncio
from types import SimpleNamespace as NS

import pytest

from src.catalog.draft import planner as planner_mod
from src.catalog.draft.planner import (
    MAX_PACKS,
    MAX_QUERIES,
    MAX_QUERY_CHARS,
    DraftPlan,
    DraftPlanner,
)


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.prompts: list[str] = []

    async def complete_json(self, prompt, system):
        self.prompts.append(prompt)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakePacks:
    def __init__(self, rows):
        self.rows, self.calls = rows, 0

    async def list_candidates(self):
        self.calls += 1
        return self.rows


ROWS = [NS(id=i, name=f"Pack {i}", description=f"desc {i}") for i in range(1, 6)]


def plan(result, intent="make a skill", pick_packs=True, rows=ROWS):
    llm, repo = FakeLLM(result), FakePacks(rows)
    out = asyncio.run(DraftPlanner(llm, repo).plan(intent, pick_packs))
    return out, llm, repo

def test_prompt_lists_packs_as_closed_list():
    _, llm, _ = plan({"pack_keys": [], "queries": []})
    p = llm.prompts[0]
    assert p.startswith("User request: make a skill")
    assert "- pack:1: Pack 1 - desc 1" in p and "- pack:5: Pack 5 - desc 5" in p


def test_pick_packs_false_does_not_touch_the_repo_and_lists_nothing():
    out, llm, repo = plan({"pack_keys": ["pack:1"], "queries": ["docker compose"]}, pick_packs=False)
    assert repo.calls == 0
    assert "pack:1:" not in llm.prompts[0] and "not needed" in llm.prompts[0]
    assert out.pack_ids == [] and out.queries == ["docker compose"]  # key is not valid -> dropped


def test_no_packs_in_catalog_behaves_like_pick_packs_false():
    out, llm, _ = plan({"pack_keys": ["pack:1"], "queries": ["q"]}, rows=[])
    assert "not needed" in llm.prompts[0] and out.pack_ids == []

def test_valid_plan():
    out, *_ = plan({"pack_keys": ["pack:2", "pack:1"], "queries": ["docker compose", "service networking"]})
    assert out == DraftPlan([2, 1], ["docker compose", "service networking"])


@pytest.mark.parametrize("key", ["pack:999", "skill:1", "Pack:1", "pack:", "pack: 1", "pack:1 ", "pack:-1", 1, None, ["pack:1"]])
def test_invalid_pack_keys_are_dropped_not_fatal(key):
    out, *_ = plan({"pack_keys": [key, "pack:3"], "queries": ["q"]})
    assert out.pack_ids == [3]


def test_duplicate_pack_keys_collapse_and_order_is_kept():
    out, *_ = plan({"pack_keys": ["pack:3", "pack:1", "pack:3"], "queries": []})
    assert out.pack_ids == [3, 1]


def test_pack_cap():
    out, *_ = plan({"pack_keys": [f"pack:{i}" for i in range(1, 6)], "queries": []})
    assert out.pack_ids == [1, 2, 3][:MAX_PACKS] and len(out.pack_ids) == MAX_PACKS


def test_queries_are_normalized_deduplicated_and_capped():
    raw = {"pack_keys": [], "queries": ["  a   b ", "a b", "", "   ", 5, None, "c", "d", "e"]}
    out, *_ = plan(raw)
    assert out.queries == ["a b", "c", "d"][:MAX_QUERIES]


def test_long_query_is_truncated():
    out, *_ = plan({"pack_keys": [], "queries": ["w " * 200]})
    assert len(out.queries[0]) <= MAX_QUERY_CHARS


@pytest.mark.parametrize("raw", [None, [], "text", 5])
def test_non_object_response_gives_empty_plan(raw):
    assert plan(raw)[0] == DraftPlan()


@pytest.mark.parametrize("raw", [{}, {"pack_keys": None, "queries": None}, {"pack_keys": [], "queries": []}])
def test_missing_or_null_lists_give_empty_plan(raw):
    assert plan(raw)[0] == DraftPlan()


@pytest.mark.xfail(
    strict=True,
    reason="DraftPlanner._parse iterates a bare string/dict: 'docker' -> queries ['d','o','c']. "
    "Fix: `if not isinstance(value, list): value = []` for pack_keys and queries.",
)
@pytest.mark.parametrize(
    "raw",
    [
        {"pack_keys": "pack:1", "queries": "docker"},
        {"pack_keys": {"pack:1": 1}, "queries": {"docker compose": 1}},
    ],
)
def test_non_list_pack_keys_and_queries_are_ignored(raw):
    assert plan(raw)[0] == DraftPlan()

def test_llm_exception_degrades_to_empty_plan():
    assert plan(RuntimeError("boom"))[0] == DraftPlan()


def test_timeout_degrades_to_empty_plan(monkeypatch):
    monkeypatch.setattr(planner_mod, "PLAN_TIMEOUT", 0.01)

    class Slow:
        async def complete_json(self, prompt, system):
            await asyncio.sleep(1)

    out = asyncio.run(DraftPlanner(Slow(), FakePacks(ROWS)).plan("x"))
    assert out == DraftPlan()
