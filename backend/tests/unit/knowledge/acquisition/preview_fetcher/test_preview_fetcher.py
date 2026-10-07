from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
import hashlib

import fitz
import pytest

from src.knowledge.acquisition.dedup.url_normalizer import calculate_hash
from src.knowledge.acquisition.fetch import Fetcher
from src.knowledge.acquisition.preview_fetcher.preview_fetrcher import PreviewFetcher
from src.knowledge.documents_schema.discovery_model import DiscoveryResult
from src.knowledge.documents_schema.document_candidate import DocumentCandidate
from src.knowledge.documents_schema.raw_document import RawDocument


def make_raw(content, content_type="text/html", source="https://example.com/a"):
    if isinstance(content, str):
        content = content.encode()
    return RawDocument(
        source=source,
        content=content,
        content_type=content_type,
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at=datetime.now(timezone.utc),
    )


def make_candidate(url="https://example.com/a", title="Title", snippet="Snippet"):
    return DiscoveryResult(
        title=title, url=url, domain="example.com", snippet=snippet, mime_type="text/html"
    )


def make_pdf(text="Hello PDF", toc=None) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    if toc:
        doc.set_toc(toc)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def mock_fetcher():
    fetcher = MagicMock(spec=Fetcher)
    fetcher.fetch = AsyncMock()
    return fetcher


@pytest.fixture
def preview_fetcher(mock_fetcher):
    return PreviewFetcher(fetcher=mock_fetcher)


class TestParseHtml:

    def test_extracts_headings_h1_to_h3(self, preview_fetcher):
        html = "<h1>One</h1><h2>Two</h2><h3>Three</h3><h4>Skip</h4><p>body</p>"

        headings, _ = preview_fetcher._parse_preview(make_raw(html))

        assert headings == ["One", "Two", "Three"]

    def test_skips_empty_headings(self, preview_fetcher):
        headings, _ = preview_fetcher._parse_preview(make_raw("<h1>  </h1><h2>Real</h2>"))

        assert headings == ["Real"]

    def test_limits_headings(self, mock_fetcher):
        pf = PreviewFetcher(mock_fetcher, max_headings=2)
        html = "".join(f"<h2>H{i}</h2>" for i in range(5))

        headings, _ = pf._parse_preview(make_raw(html))

        assert headings == ["H0", "H1"]

    def test_truncates_first_page(self, mock_fetcher):
        pf = PreviewFetcher(mock_fetcher, preview_chars=10)

        _, first_page = pf._parse_preview(make_raw("<p>" + "a" * 100 + "</p>"))

        assert first_page == "a" * 10

    def test_collapses_tags_into_spaced_text(self, preview_fetcher):
        _, first_page = preview_fetcher._parse_preview(make_raw("<p>Hello</p><p>World</p>"))

        assert first_page == "Hello World"


class TestParsePdf:

    def test_extracts_first_page_text(self, preview_fetcher):
        _, first_page = preview_fetcher._parse_preview(
            make_raw(make_pdf("Distributed systems"), "application/pdf")
        )

        assert "Distributed systems" in first_page

    def test_extracts_toc_as_headings(self, preview_fetcher):
        pdf = make_pdf(toc=[[1, "Intro", 1], [2, "Details", 1]])

        headings, _ = preview_fetcher._parse_preview(make_raw(pdf, "application/pdf"))

        assert headings == ["Intro", "Details"]

    def test_pdf_without_toc_has_no_headings(self, preview_fetcher):
        headings, _ = preview_fetcher._parse_preview(make_raw(make_pdf(), "application/pdf"))

        assert headings == []

    def test_truncates_first_page(self, mock_fetcher):
        pf = PreviewFetcher(mock_fetcher, preview_chars=5)

        _, first_page = pf._parse_preview(make_raw(make_pdf("abcdefghij"), "application/pdf"))

        assert len(first_page) == 5

    def test_zero_page_pdf_returns_empty(self, preview_fetcher, monkeypatch):
        fake_pdf = SimpleNamespace(page_count=0)
        context = MagicMock()
        context.__enter__.return_value = fake_pdf
        monkeypatch.setattr(fitz, "open", lambda **kwargs: context)

        assert preview_fetcher._parse_preview(make_raw(b"x", "application/pdf")) == ([], "")


class TestParsePlainText:

    def test_cleans_whitespace_and_has_no_headings(self, preview_fetcher):
        headings, first_page = preview_fetcher._parse_preview(
            make_raw("hello\n\n   world\t!", "text/plain")
        )

        assert headings == []
        assert first_page == "hello world !"

    def test_unknown_type_falls_back_to_plain_text(self, preview_fetcher):
        _, first_page = preview_fetcher._parse_preview(make_raw("some text", "application/json"))

        assert first_page == "some text"

    def test_invalid_utf8_is_ignored(self, preview_fetcher):
        _, first_page = preview_fetcher._parse_preview(make_raw(b"ok\xff\xfe!", "text/plain"))

        assert first_page == "ok!"

    def test_truncates(self, mock_fetcher):
        pf = PreviewFetcher(mock_fetcher, preview_chars=4)

        assert pf._parse_preview(make_raw("abcdefgh", "text/plain"))[1] == "abcd"


class TestFetchMany:

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty_list(self, preview_fetcher, mock_fetcher):
        assert await preview_fetcher.fetch_many([], "q") == []
        mock_fetcher.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_builds_document_candidate(self, preview_fetcher, mock_fetcher):
        candidate = make_candidate(title="My title", snippet="My snippet")
        mock_fetcher.fetch = AsyncMock(return_value=make_raw("<h1>Head</h1><p>Body</p>"))

        result = await preview_fetcher.fetch_many([candidate], "my query")

        assert len(result) == 1
        doc = result[0]
        assert isinstance(doc, DocumentCandidate)
        assert doc.key == calculate_hash(candidate)
        assert doc.query == "my query"
        assert doc.title == "My title"
        assert doc.url == candidate.url
        assert doc.domain == "example.com"
        assert doc.snippet == "My snippet"
        assert doc.headings == ["Head"]
        assert "Body" in doc.first_page

    @pytest.mark.asyncio
    async def test_failed_fetches_are_skipped(self, preview_fetcher, mock_fetcher):
        good, bad = make_candidate("https://good.com"), make_candidate("https://bad.com")

        async def fetch(url):
            if "bad" in url:
                raise ConnectionError("down")
            return make_raw("<p>ok</p>", source=url)

        mock_fetcher.fetch = AsyncMock(side_effect=fetch)

        result = await preview_fetcher.fetch_many([bad, good], "q")

        assert [d.url for d in result] == ["https://good.com"]

    @pytest.mark.asyncio
    async def test_parse_errors_are_skipped_too(self, preview_fetcher, mock_fetcher):
        mock_fetcher.fetch = AsyncMock(return_value=make_raw(b"not a pdf", "application/pdf"))

        assert await preview_fetcher.fetch_many([make_candidate()], "q") == []

    @pytest.mark.asyncio
    async def test_preserves_candidate_order(self, preview_fetcher, mock_fetcher):
        candidates = [make_candidate(f"https://s{i}.com") for i in range(3)]
        mock_fetcher.fetch = AsyncMock(side_effect=lambda url: make_raw("<p>x</p>", source=url))

        result = await preview_fetcher.fetch_many(candidates, "q")

        assert [d.url for d in result] == [c.url for c in candidates]