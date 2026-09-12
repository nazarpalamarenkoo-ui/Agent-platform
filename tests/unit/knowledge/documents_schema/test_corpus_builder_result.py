import pytest
from pydantic import ValidationError

from src.knowledge.documents_schema.corpus_build_result import CorpusBuilderResult


class TestCorpusBuilderResult:

    def test_creates_with_valid_data(self):
        result = CorpusBuilderResult(
            succeeded=[1, 2, 3],
            skipped_duplicates=["https://a.com"],
            failed=[{"source": "https://b.com", "error": "boom"}],
        )

        assert result.succeeded == [1, 2, 3]
        assert result.skipped_duplicates == ["https://a.com"]
        assert result.failed == [{"source": "https://b.com", "error": "boom"}]

    def test_accepts_all_empty_lists(self):
        result = CorpusBuilderResult(succeeded=[], skipped_duplicates=[], failed=[])

        assert result.succeeded == []
        assert result.skipped_duplicates == []
        assert result.failed == []

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            CorpusBuilderResult(succeeded=[], skipped_duplicates=[])

    def test_succeeded_must_be_list_of_ints(self):
        with pytest.raises(ValidationError):
            CorpusBuilderResult(succeeded=["not-an-int"], skipped_duplicates=[], failed=[])

    def test_skipped_duplicates_must_be_list_of_strings(self):
        result = CorpusBuilderResult(succeeded=[], skipped_duplicates=["a", "b"], failed=[])
        assert result.skipped_duplicates == ["a", "b"]

    def test_failed_must_be_list_of_dicts(self):
        with pytest.raises(ValidationError):
            CorpusBuilderResult(succeeded=[], skipped_duplicates=[], failed=["not-a-dict"])

    def test_failed_accepts_arbitrary_dict_shape(self):
        result = CorpusBuilderResult(
            succeeded=[],
            skipped_duplicates=[],
            failed=[{"source": "x", "error": "y", "extra": 123}],
        )
        assert result.failed[0]["extra"] == 123