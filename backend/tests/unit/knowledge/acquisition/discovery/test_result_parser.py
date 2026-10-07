import pytest

from src.knowledge.acquisition.discovery.result_parser import ResultParser
from src.knowledge.documents_schema.discovery_model import DiscoveryResult
from src.knowledge.documents_schema.search_schema import SearchResult


def make_search_result(url="https://example.com/a", title="Title", snippet="Snippet"):
    return SearchResult(url=url, title=title, snippet=snippet)


@pytest.fixture
def parser():
    return ResultParser()


class TestExtractDomain:

    def test_strips_www_and_lowercases(self, parser):
        assert parser._extract_domain("https://www.Example.COM/path") == "example.com"

    def test_keeps_subdomain(self, parser):
        assert parser._extract_domain("https://docs.python.org/3/") == "docs.python.org"

    def test_empty_url_returns_unknown(self, parser):
        assert parser._extract_domain("") == "unknown"


class TestGuessMimeType:

    def test_pdf_extension(self, parser):
        assert parser._guess_mime_type("https://example.com/paper.pdf") == "application/pdf"

    def test_no_extension_defaults_to_html(self, parser):
        assert parser._guess_mime_type("https://example.com/article") == "text/html"

    def test_txt_extension(self, parser):
        assert parser._guess_mime_type("https://example.com/readme.txt") == "text/plain"


class TestParseMany:

    def test_converts_search_results_to_discovery_results(self, parser):
        result = parser.parse_many([make_search_result("https://www.arxiv.org/pdf/1.pdf", "Paper", "Abstract")])

        assert len(result) == 1
        item = result[0]
        assert isinstance(item, DiscoveryResult)
        assert item.title == "Paper"
        assert item.url == "https://www.arxiv.org/pdf/1.pdf"
        assert item.domain == "arxiv.org"
        assert item.snippet == "Abstract"
        assert item.mime_type == "application/pdf"

    def test_skips_results_without_url(self, parser):
        results = parser.parse_many([make_search_result(url=""), make_search_result("https://ok.com")])

        assert [r.url for r in results] == ["https://ok.com"]

    def test_empty_input_returns_empty_list(self, parser):
        assert parser.parse_many([]) == []

    def test_preserves_order(self, parser):
        urls = [f"https://site{i}.com" for i in range(4)]

        results = parser.parse_many([make_search_result(u) for u in urls])

        assert [r.url for r in results] == urls