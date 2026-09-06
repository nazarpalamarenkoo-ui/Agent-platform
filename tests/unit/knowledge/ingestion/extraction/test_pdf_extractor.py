from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.knowledge.ingestion.extraction.pdf_extractor import PdfExtractor
from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument


def make_raw_document(content=b"%PDF-1.4 fake", source="https://example.com/doc.pdf"):
    return RawDocument(
        source=source,
        content=content,
        content_type="application/pdf",
        content_hash="a" * 64,
        fetched_at=datetime.now(timezone.utc),
    )


def make_fake_pdf(pages_text):
    """Build a MagicMock standing in for a fitz.Document context manager."""
    fake_pages = []
    for text in pages_text:
        page = MagicMock()
        page.get_text.return_value = text
        fake_pages.append(page)

    fake_pdf = MagicMock()
    fake_pdf.page_count = len(pages_text)
    fake_pdf.__getitem__.side_effect = lambda i: fake_pages[i]
    fake_pdf.__enter__.return_value = fake_pdf
    fake_pdf.__exit__.return_value = False
    return fake_pdf


class TestPdfExtractor:

    def test_extracts_text_from_all_pages(self):
        raw_doc = make_raw_document()
        fake_pdf = make_fake_pdf(["Page one text", "Page two text"])

        with patch(
            "src.knowledge.ingestion.extraction.pdf_extractor.fitz.open",
            return_value=fake_pdf,
        ) as mock_open:
            result = PdfExtractor().extract(raw_doc)

        mock_open.assert_called_once_with(stream=raw_doc.content, filetype="pdf")
        assert isinstance(result, ExtractedDocument)
        assert result.text == "Page one text\n\nPage two text"

    def test_metadata_contains_page_count_pages_and_source(self):
        raw_doc = make_raw_document(source="https://example.com/report.pdf")
        fake_pdf = make_fake_pdf(["A", "B", "C"])

        with patch(
            "src.knowledge.ingestion.extraction.pdf_extractor.fitz.open",
            return_value=fake_pdf,
        ):
            result = PdfExtractor().extract(raw_doc)

        assert result.metadata["page_count"] == 3
        assert result.metadata["source"] == "https://example.com/report.pdf"
        assert result.metadata["pages"] == [
            {"page": 0, "text": "A"},
            {"page": 1, "text": "B"},
            {"page": 2, "text": "C"},
        ]

    def test_handles_single_page_document(self):
        raw_doc = make_raw_document()
        fake_pdf = make_fake_pdf(["only page"])

        with patch(
            "src.knowledge.ingestion.extraction.pdf_extractor.fitz.open",
            return_value=fake_pdf,
        ):
            result = PdfExtractor().extract(raw_doc)

        assert result.text == "only page"
        assert result.metadata["page_count"] == 1

    def test_handles_empty_document(self):
        raw_doc = make_raw_document()
        fake_pdf = make_fake_pdf([])

        with patch(
            "src.knowledge.ingestion.extraction.pdf_extractor.fitz.open",
            return_value=fake_pdf,
        ):
            result = PdfExtractor().extract(raw_doc)

        assert result.text == ""
        assert result.metadata["page_count"] == 0
        assert result.metadata["pages"] == []