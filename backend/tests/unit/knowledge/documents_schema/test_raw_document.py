from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.knowledge.documents_schema.raw_document import RawDocument


def make_raw_document(**overrides):
    defaults = dict(
        source="https://example.com/page.html",
        content=b"hello world",
        content_type="text/html",
        content_hash="a" * 64,
        fetched_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return RawDocument(**defaults)


class TestRawDocument:

    def test_creates_with_valid_data(self):
        doc = make_raw_document()

        assert doc.source == "https://example.com/page.html"
        assert doc.content == b"hello world"
        assert doc.content_type == "text/html"
        assert doc.content_hash == "a" * 64
        assert isinstance(doc.fetched_at, datetime)

    def test_content_hash_too_short_raises(self):
        with pytest.raises(ValidationError):
            make_raw_document(content_hash="short")

    def test_content_hash_too_long_raises(self):
        with pytest.raises(ValidationError):
            make_raw_document(content_hash="a" * 65)

    def test_content_hash_exact_length_boundaries(self):
        doc = make_raw_document(content_hash="f" * 64)
        assert len(doc.content_hash) == 64

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            RawDocument(
                content=b"data",
                content_type="text/plain",
                content_hash="a" * 64,
                fetched_at=datetime.now(timezone.utc),
            )

    def test_content_accepts_empty_bytes(self):
        doc = make_raw_document(content=b"")
        assert doc.content == b""

    def test_content_rejects_non_bytes_string_without_coercion_error(self):
        doc = make_raw_document(content="hello")
        assert doc.content == b"hello"