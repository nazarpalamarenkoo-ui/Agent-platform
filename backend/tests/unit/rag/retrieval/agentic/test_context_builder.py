from src.rag.retrieval.agentic.context_builder import ContextBuilder
from src.rag.retrieval.agentic.models import RetrievalEvidence


def ev(chunk_id, score=0.5, text=None, query="q"):
    return RetrievalEvidence(
        query=query,
        chunk_id=chunk_id,
        score=score,
        text=text if text is not None else f"text-{chunk_id}",
    )


class TestInit:

    def test_defaults(self):
        b = ContextBuilder()
        assert b.max_chunks == 10
        assert b.max_chars == 20_000

    def test_custom_values(self):
        b = ContextBuilder(max_chunks=3, max_chars=100)
        assert b.max_chunks == 3
        assert b.max_chars == 100


class TestDeduplicate:

    def test_removes_duplicate_chunk_ids(self):
        result = ContextBuilder()._deduplicate([ev("a"), ev("a"), ev("b")])
        assert sorted(e.chunk_id for e in result) == ["a", "b"]

    def test_keeps_highest_score_for_duplicates(self):
        result = ContextBuilder()._deduplicate(
            [ev("a", 0.3, query="q1"), ev("a", 0.9, query="q2"), ev("a", 0.5, query="q3")]
        )
        assert len(result) == 1
        assert result[0].score == 0.9
        assert result[0].query == "q2"

    def test_first_occurrence_wins_on_equal_score(self):
        result = ContextBuilder()._deduplicate(
            [ev("a", 0.5, query="first"), ev("a", 0.5, query="second")]
        )
        assert result[0].query == "first"

    def test_empty_input(self):
        assert ContextBuilder()._deduplicate([]) == []


class TestSortByScore:

    def test_sorts_descending(self):
        result = ContextBuilder()._sort_by_score([ev("a", 0.1), ev("b", 0.9), ev("c", 0.5)])
        assert [e.chunk_id for e in result] == ["b", "c", "a"]

    def test_stable_for_ties(self):
        result = ContextBuilder()._sort_by_score([ev("a", 0.5), ev("b", 0.5)])
        assert [e.chunk_id for e in result] == ["a", "b"]


class TestTruncate:

    def test_limits_by_max_chunks(self):
        b = ContextBuilder(max_chunks=2)
        result = b._truncate([ev(str(i)) for i in range(5)])
        assert [e.chunk_id for e in result] == ["0", "1"]

    def test_limits_by_max_chars(self):
        b = ContextBuilder(max_chars=25)
        result = b._truncate([ev("a", text="x" * 10), ev("b", text="y" * 10), ev("c", text="z" * 10)])
        assert [e.chunk_id for e in result] == ["a", "b"]

    def test_total_exactly_max_chars_is_allowed(self):
        b = ContextBuilder(max_chars=20)
        result = b._truncate([ev("a", text="x" * 10), ev("b", text="y" * 10)])
        assert len(result) == 2

    def test_stops_at_first_chunk_that_does_not_fit(self):
        # поведінка: break, а не continue — менший chunk після великого не потрапляє
        b = ContextBuilder(max_chars=15)
        result = b._truncate(
            [ev("a", text="x" * 10), ev("big", text="y" * 10), ev("small", text="z" * 2)]
        )
        assert [e.chunk_id for e in result] == ["a"]

    def test_single_chunk_larger_than_max_chars_yields_empty(self):
        b = ContextBuilder(max_chars=5)
        assert b._truncate([ev("a", text="x" * 10)]) == []

    def test_empty_input(self):
        assert ContextBuilder()._truncate([]) == []


class TestFormat:

    def test_empty_returns_empty_string(self):
        assert ContextBuilder()._format([]) == ""

    def test_single_block_format(self):
        out = ContextBuilder()._format([ev("a", 0.9, text="hello")])
        assert out == "[Source 1] (score: 0.90)\nhello\n"

    def test_multiple_blocks_numbered_in_order(self):
        out = ContextBuilder()._format([ev("a", 0.9, text="A"), ev("b", 0.5, text="B")])
        assert out.index("[Source 1] (score: 0.90)") < out.index("[Source 2] (score: 0.50)")
        assert "\nA\n" in out and "\nB\n" in out

    def test_score_formatted_with_two_decimals(self):
        out = ContextBuilder()._format([ev("a", 0.123456, text="t")])
        assert "(score: 0.12)" in out


class TestBuildEvidenceList:

    def test_dedup_sort_truncate_pipeline(self):
        b = ContextBuilder(max_chunks=2)
        result = b.build_evidence_list(
            [ev("a", 0.2), ev("b", 0.9), ev("a", 0.8), ev("c", 0.1)]
        )
        assert [(e.chunk_id, e.score) for e in result] == [("b", 0.9), ("a", 0.8)]

    def test_empty_input(self):
        assert ContextBuilder().build_evidence_list([]) == []

    def test_does_not_mutate_input(self):
        original = [ev("a", 0.2), ev("a", 0.8), ev("b", 0.5)]
        snapshot = list(original)
        ContextBuilder().build_evidence_list(original)
        assert original == snapshot


class TestBuild:

    def test_returns_formatted_string_of_cleaned_evidence(self):
        b = ContextBuilder(max_chunks=1)
        out = b.build([ev("a", 0.3, text="low"), ev("b", 0.9, text="high")])
        assert out == "[Source 1] (score: 0.90)\nhigh\n"

    def test_empty_evidence_returns_empty_string(self):
        assert ContextBuilder().build([]) == ""