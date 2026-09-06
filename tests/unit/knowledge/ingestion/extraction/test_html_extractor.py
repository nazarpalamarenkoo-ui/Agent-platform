from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.knowledge.ingestion.extraction.html_extractor import HTMLExtractor
from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument


def make_raw_document(content=b"<html><body>hi</body></html>", source="https://example.com"):
    return RawDocument(
        source=source,
        content=content,
        content_type="text/html",
        content_hash="a" * 64,
        fetched_at=datetime.now(timezone.utc),
    )


class TestHTMLExtractor:

    def test_extracts_text_using_trafilatura(self):
        raw_doc = make_raw_document()

        with patch(
            "src.knowledge.ingestion.extraction.html_extractor.trafilatura.extract",
            return_value="Extracted article text",
        ) as mock_extract:
            result = HTMLExtractor().extract(raw_doc)

        assert isinstance(result, ExtractedDocument)
        assert result.text == "Extracted article text"
        mock_extract.assert_called_once_with(
            raw_doc.content, include_comments=False, include_tables=True, no_fallback=False
        )

    def test_includes_source_in_metadata(self):
        raw_doc = make_raw_document(source="https://example.com/article")

        with patch(
            "src.knowledge.ingestion.extraction.html_extractor.trafilatura.extract",
            return_value="text",
        ):
            result = HTMLExtractor().extract(raw_doc)

        assert result.metadata == {"source": "https://example.com/article"}

    def test_falls_back_to_empty_string_when_extraction_returns_none(self):
        raw_doc = make_raw_document()

        with patch(
            "src.knowledge.ingestion.extraction.html_extractor.trafilatura.extract",
            return_value=None,
        ):
            result = HTMLExtractor().extract(raw_doc)

        assert result.text == ""

    def test_falls_back_to_empty_string_when_extraction_returns_empty_string(self):
        raw_doc = make_raw_document()

        with patch(
            "src.knowledge.ingestion.extraction.html_extractor.trafilatura.extract",
            return_value="",
        ):
            result = HTMLExtractor().extract(raw_doc)

        assert result.text == ""