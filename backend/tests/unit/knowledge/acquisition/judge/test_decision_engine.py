import pytest

from src.knowledge.acquisition.judge.decision_engine import DecisionEngine
from src.knowledge.acquisition.judge.models import (
    DecidedSource,
    DocumentDecision,
    JudgeSource,
    TrustBreakdown,
)


def make_source(edu=0.5, impl=0.5, auth=0.5, category="tutorial"):
    return JudgeSource(
        key="k",
        url="https://example.com",
        title="t",
        trust=TrustBreakdown(educational=edu, implementation=impl, authority=auth),
        document_category=category,
        reason="r",
    )


@pytest.fixture
def engine():
    return DecisionEngine()


class TestInit:

    def test_default_weights_sum_to_one(self, engine):
        total = engine.educational_weight + engine.implementation_weight + engine.authority_weight
        assert total == pytest.approx(1.0)

    def test_rejects_weights_not_summing_to_one(self):
        with pytest.raises(ValueError, match="sum"):
            DecisionEngine(educational_weight=0.5, implementation_weight=0.5, authority_weight=0.5)

    @pytest.mark.parametrize("threshold", [-0.1, 1.1])
    def test_rejects_threshold_out_of_range(self, threshold):
        with pytest.raises(ValueError, match="acceptance_threshold"):
            DecisionEngine(acceptance_threshold=threshold)

    @pytest.mark.parametrize("threshold", [0.0, 1.0])
    def test_accepts_boundary_thresholds(self, threshold):
        assert DecisionEngine(acceptance_threshold=threshold).acceptance_threshold == threshold


class TestCalculateOverall:

    def test_weighted_sum(self, engine):
        trust = TrustBreakdown(educational=0.9, implementation=0.6, authority=0.3)

        assert engine._calculate_overall(trust) == pytest.approx(0.675)

    def test_result_is_rounded_to_three_decimals(self, engine):
        trust = TrustBreakdown(educational=0.333, implementation=0.333, authority=0.333)

        assert engine._calculate_overall(trust) == 0.333

    def test_educational_weight_dominates(self, engine):
        trust = TrustBreakdown(educational=1.0, implementation=0.0, authority=0.0)

        assert engine._calculate_overall(trust) == pytest.approx(0.45)

    def test_custom_weights(self):
        engine = DecisionEngine(educational_weight=0.0, implementation_weight=0.0, authority_weight=1.0)
        trust = TrustBreakdown(educational=0.1, implementation=0.1, authority=0.9)

        assert engine._calculate_overall(trust) == 0.9


class TestDecide:

    def test_accepts_above_threshold(self, engine):
        decided = engine.decide(make_source(0.9, 0.9, 0.9))

        assert isinstance(decided, DecidedSource)
        assert decided.decision == DocumentDecision.ACCEPT
        assert decided.overall_score == pytest.approx(0.9)

    def test_accepts_exactly_at_threshold(self, engine):
        assert engine.decide(make_source(0.75, 0.75, 0.75)).decision == DocumentDecision.ACCEPT

    def test_rejects_below_threshold(self, engine):
        assert engine.decide(make_source(0.74, 0.74, 0.74)).decision == DocumentDecision.REJECT

    def test_judge_error_is_always_rejected_with_zero_score(self, engine):
        decided = engine.decide(make_source(1.0, 1.0, 1.0, category="judge_error"))

        assert decided.decision == DocumentDecision.REJECT
        assert decided.overall_score == 0.0

    def test_keeps_original_source(self, engine):
        source = make_source()

        assert engine.decide(source).source is source

    def test_custom_threshold(self):
        engine = DecisionEngine(acceptance_threshold=0.3)

        assert engine.decide(make_source(0.4, 0.4, 0.4)).decision == DocumentDecision.ACCEPT


class TestDecideMany:

    def test_empty_list(self, engine):
        assert engine.decide_many([]) == []

    def test_decides_each_source_in_order(self, engine):
        sources = [make_source(0.9, 0.9, 0.9), make_source(0.1, 0.1, 0.1)]

        decided = engine.decide_many(sources)

        assert [d.decision for d in decided] == [DocumentDecision.ACCEPT, DocumentDecision.REJECT]