import pytest
from pydantic import ValidationError

from src.rag.retrieval.agentic.models import (
    AgenticContext,
    IterationRecord,
    RetrievalEvaluation,
    RetrievalEvidence,
    SearchPlan,
    to_evidence,
)
from src.rag.storage.base_vector_store import VectorSearchResult


def make_evaluation(**overrides):
    data = dict(sufficient=True, coverage=0.8, confidence=0.7, redundancy=0.1)
    data.update(overrides)
    return RetrievalEvaluation(**data)


class TestSearchPlan:

    def test_keeps_subqueries_when_under_limit(self):
        plan = SearchPlan(subqueries=["a", "b", "c"])
        assert plan.subqueries == ["a", "b", "c"]

    def test_keeps_exactly_five_subqueries(self):
        plan = SearchPlan(subqueries=list("abcde"))
        assert plan.subqueries == list("abcde")

    def test_truncates_to_five_subqueries(self):
        plan = SearchPlan(subqueries=list("abcdefgh"))
        assert plan.subqueries == list("abcde")

    def test_empty_subqueries_allowed(self):
        assert SearchPlan(subqueries=[]).subqueries == []

    def test_reasoning_defaults_to_empty_string(self):
        assert SearchPlan(subqueries=["a"]).reasoning == ""

    def test_subqueries_required(self):
        with pytest.raises(ValidationError):
            SearchPlan()


class TestRetrievalEvidence:

    def test_metadata_defaults_to_empty_dict(self):
        ev = RetrievalEvidence(query="q", chunk_id="1", score=0.5, text="t")
        assert ev.metadata == {}

    def test_metadata_default_is_not_shared_between_instances(self):
        a = RetrievalEvidence(query="q", chunk_id="1", score=0.5, text="t")
        b = RetrievalEvidence(query="q", chunk_id="2", score=0.5, text="t")
        a.metadata["x"] = 1
        assert b.metadata == {}


class TestRetrievalEvaluation:

    def test_valid_evaluation_with_defaults(self):
        ev = make_evaluation()
        assert ev.missing_topics == []
        assert ev.retry_queries == []

    @pytest.mark.parametrize("field", ["coverage", "confidence", "redundancy"])
    @pytest.mark.parametrize("value", [-0.01, 1.01])
    def test_out_of_range_values_rejected(self, field, value):
        with pytest.raises(ValidationError):
            make_evaluation(**{field: value})

    @pytest.mark.parametrize("field", ["coverage", "confidence", "redundancy"])
    @pytest.mark.parametrize("value", [0.0, 1.0])
    def test_boundary_values_accepted(self, field, value):
        assert getattr(make_evaluation(**{field: value}), field) == value

    def test_list_defaults_not_shared(self):
        a = make_evaluation()
        b = make_evaluation()
        a.missing_topics.append("x")
        assert b.missing_topics == []


class TestIterationRecord:

    def test_stores_fields(self):
        evaluation = make_evaluation()
        rec = IterationRecord(
            iteration=2,
            subqueries=["a"],
            new_evidence_count=3,
            total_evidence_count=7,
            evaluation=evaluation,
        )
        assert rec.iteration == 2
        assert rec.subqueries == ["a"]
        assert rec.new_evidence_count == 3
        assert rec.total_evidence_count == 7
        assert rec.evaluation == evaluation


class TestAgenticContext:

    def test_defaults(self):
        ctx = AgenticContext(original_query="q", plan=SearchPlan(subqueries=["q"]))
        assert ctx.evidence == []
        assert ctx.evaluation is None
        assert ctx.iteration == 1
        assert ctx.iterations == []

    def test_list_defaults_not_shared(self):
        plan = SearchPlan(subqueries=["q"])
        a = AgenticContext(original_query="q", plan=plan)
        b = AgenticContext(original_query="q", plan=plan)
        a.evidence.append(
            RetrievalEvidence(query="q", chunk_id="1", score=0.1, text="t")
        )
        assert b.evidence == []


class TestToEvidence:

    def test_maps_fields_from_result(self):
        result = VectorSearchResult(id="abc", score=0.75, payload={"text": "hello", "src": "x"})

        ev = to_evidence("my subquery", result)

        assert ev.query == "my subquery"
        assert ev.chunk_id == "abc"
        assert ev.score == 0.75
        assert ev.text == "hello"
        assert ev.metadata == {"text": "hello", "src": "x"}

    def test_converts_id_to_string(self):
        ev = to_evidence("q", VectorSearchResult(id=42, score=0.5, payload={"text": "t"}))
        assert ev.chunk_id == "42"

    def test_converts_score_to_float(self):
        ev = to_evidence("q", VectorSearchResult(id="1", score=1, payload={"text": "t"}))
        assert isinstance(ev.score, float)

    def test_missing_text_defaults_to_empty_string(self):
        ev = to_evidence("q", VectorSearchResult(id="1", score=0.5, payload={"other": 1}))
        assert ev.text == ""
        assert ev.metadata == {"other": 1}