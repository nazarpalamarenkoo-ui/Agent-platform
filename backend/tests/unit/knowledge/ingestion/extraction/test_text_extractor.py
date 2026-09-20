from datetime import datetime, timezone

import pytest

from src.knowledge.ingestion.extraction.text_extractor import TextExtractor
from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument


def make_raw_document(content=b"hello world", source="https://example.com/file.txt"):
    return RawDocument(
        source=source,
        content=content,
        content_type="text/plain",
        content_hash="a" * 64,
        fetched_at=datetime.now(timezone.utc),
    )


class TestTextExtractor:

    def test_decodes_utf8_content(self):
        raw_doc = make_raw_document(content="héllo wörld".encode("utf-8"))

        result = TextExtractor().extract(raw_doc)

        assert isinstance(result, ExtractedDocument)
        assert result.text == "héllo wörld"

    def test_includes_source_in_metadata(self):
        raw_doc = make_raw_document(source="https://example.com/notes.txt")

        result = TextExtractor().extract(raw_doc)

        assert result.metadata == {"source": "https://example.com/notes.txt"}

    def test_empty_content_returns_empty_text(self):
        raw_doc = make_raw_document(content=b"")

        result = TextExtractor().extract(raw_doc)

        assert result.text == ""

    def test_invalid_utf8_raises_unicode_decode_error(self):
        raw_doc = make_raw_document(content=b"\xff\xfe\x00invalid")

        with pytest.raises(UnicodeDecodeError):
            TextExtractor().extract(raw_doc)