import pytest

from src.knowledge.acquisition.judge.exceptions import JudgeValidationError
from src.knowledge.acquisition.judge.models import JudgeItem
from src.knowledge.acquisition.judge.parse import parse


def make_raw_item(key, reason=None):
    return {
        "key": key,
        "reason": reason if reason is not None else f"specific reason for {key}",
        "document_category": "tutorial",
        "trust": {"educational": 0.8, "implementation": 0.7, "authority": 0.6},
    }


class TestParse:

    def test_returns_items_for_valid_response(self):
        raw = {"results": [make_raw_item("a"), make_raw_item("b")]}

        items = parse(raw, ["a", "b"])

        assert all(isinstance(i, JudgeItem) for i in items)
        assert [i.key for i in items] == ["a", "b"]

    def test_order_of_keys_does_not_matter(self):
        raw = {"results": [make_raw_item("b"), make_raw_item("a")]}

        assert {i.key for i in parse(raw, ["a", "b"])} == {"a", "b"}

    def test_invalid_structure_raises_validation_error(self):
        with pytest.raises(JudgeValidationError):
            parse({"wrong": []}, ["a"])

    def test_score_out_of_range_raises_validation_error(self):
        item = make_raw_item("a")
        item["trust"]["educational"] = 1.5

        with pytest.raises(JudgeValidationError):
            parse({"results": [item]}, ["a"])

    def test_missing_key_raises(self):
        with pytest.raises(JudgeValidationError, match="missing"):
            parse({"results": [make_raw_item("a")]}, ["a", "b"])

    def test_unexpected_key_raises(self):
        raw = {"results": [make_raw_item("a"), make_raw_item("zzz")]}

        with pytest.raises(JudgeValidationError, match="unexpected"):
            parse(raw, ["a"])

    def test_duplicate_key_raises(self):
        raw = {"results": [make_raw_item("a", "r1"), make_raw_item("a", "r2")]}

        with pytest.raises(JudgeValidationError, match="duplicates"):
            parse(raw, ["a"])

    def test_empty_results_with_expected_keys_raises(self):
        with pytest.raises(JudgeValidationError):
            parse({"results": []}, ["a"])


class TestReasonDiversity:

    def test_identical_reasons_raise(self):
        raw = {"results": [make_raw_item("a", "Same text"), make_raw_item("b", "Same text")]}

        with pytest.raises(JudgeValidationError, match="same reason"):
            parse(raw, ["a", "b"])

    def test_comparison_ignores_case_and_surrounding_whitespace(self):
        raw = {"results": [make_raw_item("a", "Same Text"), make_raw_item("b", "  same text  ")]}

        with pytest.raises(JudgeValidationError):
            parse(raw, ["a", "b"])

    def test_single_item_is_never_flagged(self):
        assert len(parse({"results": [make_raw_item("a", "anything")]}, ["a"])) == 1

    def test_different_reasons_pass(self):
        raw = {"results": [make_raw_item("a", "one"), make_raw_item("b", "two")]}

        assert len(parse(raw, ["a", "b"])) == 2