import asyncio
from types import SimpleNamespace as NS

import pytest

from src.catalog.draft import sources
from src.catalog.draft.sources import (
    MAX_SNIPPET_CHARS,
    MAX_SNIPPETS,
    MIN_SCORE,
    WARN_NOTHING,
    WARN_PARTIAL,
    WARN_UNAVAILABLE,
    collect_snippets,
    defang,
)

PACKS = [
    NS(id=1, slug="docker", name="Docker Documentation", domain_id=10),
    NS(id=2, slug="k8s", name="Kubernetes Documentation", domain_id=11),
]


def _hit(pack, idx, score, text="text", **extra):
    payload = {"knowledge_pack": pack, "chunk_index": idx, "text": text, **extra}
    return NS(id=f"id-{pack}-{idx}", score=score, payload=payload)


class FakeKnowledge:
    """Answers search_by_slugs per query: value is a list of hits or an Exception."""

    def __init__(self, by_query):
        self.by_query = by_query
        self.calls: list[dict] = []

    async def search_by_slugs(self, **kw):
        self.calls.append(kw)
        out = self.by_query[kw["query"]]
        if isinstance(out, BaseException):
            raise out
        return out


def run(knowledge, queries, packs=PACKS):
    return asyncio.run(collect_snippets(knowledge, queries, packs))

HIGH = MIN_SCORE + 0.2

@pytest.mark.parametrize(
    "text,expected",
    [
        ("a <retrieved_source id='x'>b</retrieved_source> c", "a b c"),
        ("<user_source>x</user_source>", "x"),
        ("<USER_SOURCE>x</USER_SOURCE>", "x"),
        ("< / user_source >", ""),
        ("<user_source\nid=1>x", "x"),
        ("plain <b>html</b> stays", "plain <b>html</b> stays"),
        ("", ""),
        (None, ""),
    ],
)
def test_defang_removes_boundary_tags_only(text, expected):
    assert defang(text) == expected


def test_defang_handles_nested_reassembled_tags():
    # removing the inner tag would otherwise re-create a valid outer tag
    assert defang("<user_<user_source>source>") == ""
    assert defang("</retrieved_</retrieved_source>source>") == ""


def test_defang_does_not_touch_lookalike_names():
    assert defang("<user_sources>") == "<user_sources>"

def test_every_query_is_searched_with_the_selected_slugs_and_limits():
    k = FakeKnowledge({"q1": [], "q2": []})
    run(k, ["q1", "q2"])
    assert {c["query"] for c in k.calls} == {"q1", "q2"}
    for c in k.calls:
        assert c["slugs"] == ["docker", "k8s"]
        assert (c["limit"], c["top_n"], c["k"]) == (sources.HYBRID_LIMIT, sources.HYBRID_TOP_N, sources.HYBRID_K)


def test_snippet_carries_pack_metadata_and_ref():
    k = FakeKnowledge({"q": [_hit("docker", 7, HIGH, "compose up")]})
    snippets, warnings = run(k, ["q"])
    assert warnings == []
    assert snippets == [
        {
            "ref": "docker#7",
            "text": "compose up",
            "score": HIGH,
            "pack_id": 1,
            "pack_slug": "docker",
            "pack_name": "Docker Documentation",
            "domain_id": 10,
        }
    ]


def test_same_chunk_from_several_queries_is_deduplicated_keeping_best_score():
    k = FakeKnowledge(
        {"a": [_hit("docker", 1, MIN_SCORE + 0.05)], "b": [_hit("docker", 1, MIN_SCORE + 0.3)]}
    )
    snippets, _ = run(k, ["a", "b"])
    assert len(snippets) == 1 and snippets[0]["score"] == pytest.approx(MIN_SCORE + 0.3)


def test_weak_snippets_are_filtered_and_boundary_score_is_kept():
    k = FakeKnowledge(
        {"q": [_hit("docker", 1, MIN_SCORE), _hit("docker", 2, MIN_SCORE - 0.01)]}
    )
    snippets, warnings = run(k, ["q"])
    assert [s["ref"] for s in snippets] == ["docker#1"]
    assert warnings == []


def test_only_weak_results_give_nothing_warning():
    k = FakeKnowledge({"q": [_hit("docker", 1, MIN_SCORE - 0.3)]})
    assert run(k, ["q"]) == ([], [WARN_NOTHING])


def test_no_results_give_nothing_warning():
    assert run(FakeKnowledge({"q": []}), ["q"]) == ([], [WARN_NOTHING])


def test_result_is_ranked_by_score_and_capped():
    hits = [_hit("docker", i, MIN_SCORE + i / 100) for i in range(MAX_SNIPPETS + 5)]
    snippets, _ = run(FakeKnowledge({"q": hits}), ["q"])
    assert len(snippets) == MAX_SNIPPETS
    scores = [s["score"] for s in snippets]
    assert scores == sorted(scores, reverse=True)


def test_text_is_truncated():
    k = FakeKnowledge({"q": [_hit("docker", 1, HIGH, "x" * (MAX_SNIPPET_CHARS + 500))]})
    assert len(run(k, ["q"])[0][0]["text"]) == MAX_SNIPPET_CHARS


def test_content_key_is_used_when_text_is_missing():
    hit = NS(id="i", score=HIGH, payload={"knowledge_pack": "docker", "chunk_index": 1, "content": "from content"})
    assert run(FakeKnowledge({"q": [hit]}), ["q"])[0][0]["text"] == "from content"


def test_chunk_index_falls_back_to_result_id():
    hit = NS(id="abc", score=HIGH, payload={"knowledge_pack": "docker", "text": "t"})
    assert run(FakeKnowledge({"q": [hit]}), ["q"])[0][0]["ref"] == "docker#abc"


@pytest.mark.parametrize(
    "hit",
    [
        NS(id=1, score=HIGH, payload={"knowledge_pack": "docker", "text": ""}),
        NS(id=2, score=HIGH, payload={"knowledge_pack": "other-pack", "text": "x"}),  # not selected
        NS(id=3, score=HIGH, payload=None),
        NS(id=4, score=HIGH, payload="str"),
    ],
)
def test_unusable_hits_are_skipped(hit):
    assert run(FakeKnowledge({"q": [hit]}), ["q"])[0] == []


def test_none_score_counts_as_zero():
    hit = NS(id=1, score=None, payload={"knowledge_pack": "docker", "text": "x"})
    assert run(FakeKnowledge({"q": [hit]}), ["q"])[0] == []


def test_all_queries_failing_means_search_unavailable():
    k = FakeKnowledge({"a": RuntimeError("down"), "b": ConnectionError("down")})
    assert run(k, ["a", "b"]) == ([], [WARN_UNAVAILABLE])


def test_some_queries_failing_keeps_results_and_warns_partial():
    k = FakeKnowledge({"a": RuntimeError("down"), "b": [_hit("docker", 1, HIGH)]})
    snippets, warnings = run(k, ["a", "b"])
    assert [s["ref"] for s in snippets] == ["docker#1"]
    assert warnings == [WARN_PARTIAL]


def test_partial_failure_with_no_strong_results_reports_both_warnings():
    k = FakeKnowledge({"a": RuntimeError("down"), "b": []})
    assert run(k, ["a", "b"])[1] == [WARN_PARTIAL, WARN_NOTHING]


def test_search_timeout_counts_as_failure(monkeypatch):
    monkeypatch.setattr(sources, "SEARCH_TIMEOUT", 0.01)

    class Slow:
        async def search_by_slugs(self, **kw):
            await asyncio.sleep(1)

    assert run(Slow(), ["q"]) == ([], [WARN_UNAVAILABLE])
