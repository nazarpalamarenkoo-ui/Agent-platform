import pytest
from pydantic import ValidationError

from src.knowledge.documents_schema.search_schema import SearchResult


class TestSearchResult:

    def test_creates_with_required_fields_only(self):
        result = SearchResult(url="https://example.com", title="Example", snippet="A snippet")

        assert result.url == "https://example.com"
        assert result.title == "Example"
        assert result.snippet == "A snippet"
        assert result.score is None
        assert result.source is None
        assert result.engines == []

    def test_creates_with_all_fields(self):
        result = SearchResult(
            url="https://example.com",
            title="Example",
            snippet="A snippet",
            score=0.87,
            source="searxng",
            engines=["google", "bing"],
        )

        assert result.score == 0.87
        assert result.source == "searxng"
        assert result.engines == ["google", "bing"]

    def test_engines_default_is_not_shared_between_instances(self):
        first = SearchResult(url="https://a.com", title="a", snippet="a")
        second = SearchResult(url="https://b.com", title="b", snippet="b")

        first.engines.append("google")

        assert first.engines == ["google"]
        assert second.engines == []

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            SearchResult(title="Example", snippet="A snippet")

    def test_score_accepts_none_explicitly(self):
        result = SearchResult(url="https://example.com", title="t", snippet="s", score=None)
        assert result.score is None