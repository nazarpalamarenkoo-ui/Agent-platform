from unittest.mock import patch

import pytest

from src.knowledge.ingestion.extraction.chunking import Chuncking
from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk


class FakeEncoder:
    """A deterministic, character-level stand-in for tiktoken's cl100k_base
    encoder so tests don't need network access to download real BPE data.
    One 'token' == one character, which makes chunk boundaries easy to
    reason about in assertions.
    """

    def encode(self, text: str) -> list[int]:
        return [ord(c) for c in text]

    def decode(self, token_ids: list[int]) -> str:
        return "".join(chr(t) for t in token_ids)


@pytest.fixture
def fake_encoder():
    return FakeEncoder()


@pytest.fixture
def chunker(fake_encoder):
    with patch(
        "src.knowledge.ingestion.extraction.chunking.tiktoken.get_encoding",
        return_value=fake_encoder,
    ):
        return Chuncking(chunk_size=10, overlap=2)


def make_extracted(text, metadata=None):
    return ExtractedDocument(text=text, metadata=metadata or {})


class TestChunckingInit:

    def test_uses_cl100k_base_encoding(self, fake_encoder):
        with patch(
            "src.knowledge.ingestion.extraction.chunking.tiktoken.get_encoding",
            return_value=fake_encoder,
        ) as mock_get_encoding:
            Chuncking()

        mock_get_encoding.assert_called_once_with("cl100k_base")

    def test_default_chunk_size_and_overlap(self, fake_encoder):
        with patch(
            "src.knowledge.ingestion.extraction.chunking.tiktoken.get_encoding",
            return_value=fake_encoder,
        ):
            chunker = Chuncking()

        assert chunker.chunk_size == 512
        assert chunker.overlap == 64


class TestChunk:

    def test_empty_text_returns_no_chunks(self, chunker):
        result = chunker.chunk(make_extracted(""))
        assert result == []

    def test_text_shorter_than_step_produces_single_chunk(self, chunker):
        # chunk_size=10, overlap=2 -> step=8; text shorter than the step
        # means the loop's second window start is already past the text.
        text = "short"  # 5 chars
        result = chunker.chunk(make_extracted(text))

        assert len(result) == 1
        assert isinstance(result[0], KnowledgeChunk)
        assert result[0].text == text
        assert result[0].token_count == 5
        assert result[0].chunk_index == 0
        assert result[0].document_id is None

    def test_text_equal_to_chunk_size_still_yields_a_trailing_overlap_chunk(self, chunker):
        # chunk_size=10, overlap=2 -> step=8. With 10 chars of text the loop
        # starts a second window at index 8, producing a short tail chunk
        # from the overlapping region. This documents the chunker's actual
        # (slightly redundant) behavior rather than an idealized one.
        text = "short text"  # 10 chars
        result = chunker.chunk(make_extracted(text))

        assert len(result) == 2
        assert result[0].text == text
        assert result[1].text == text[8:]

    def test_text_longer_than_chunk_size_produces_overlapping_chunks(self, chunker):
        # chunk_size=10, overlap=2 -> step=8
        text = "0123456789ABCDEFGHIJ"  # 20 chars
        result = chunker.chunk(make_extracted(text))

        assert [c.chunk_index for c in result] == list(range(len(result)))
        # first chunk is the first 10 chars
        assert result[0].text == "0123456789"
        # second chunk starts at step=8, so overlaps the first by 2 chars
        assert result[1].text == text[8:18]

    def test_chunk_indices_are_sequential(self, chunker):
        text = "x" * 50
        result = chunker.chunk(make_extracted(text))

        assert [c.chunk_index for c in result] == list(range(len(result)))

    def test_includes_source_in_metadata(self, chunker):
        text = "some content"
        result = chunker.chunk(make_extracted(text, metadata={"source": "doc.txt"}))

        assert all(c.metadata["source"] == "doc.txt" for c in result)

    def test_page_metadata_none_when_no_pages_present(self, chunker):
        text = "some content without page info"
        result = chunker.chunk(make_extracted(text, metadata={"source": "doc.txt"}))

        assert all(c.metadata["page"] is None for c in result)

    def test_page_metadata_resolved_from_pages(self, chunker):
        # chunk_size=10, overlap=2, step=8
        text = "0123456789ABCDEFGHIJ"  # 20 chars total
        pages = [
            {"page": 0, "text": "0123456789"},   # first 10 chars
            {"page": 1, "text": "ABCDEFGHIJ"},    # next 10 chars
        ]
        result = chunker.chunk(make_extracted(text, metadata={"source": "doc.pdf", "pages": pages}))

        assert result[0].metadata["page"] == 0
        # later chunks that start past the first page's char range should
        # resolve to page 1
        assert result[-1].metadata["page"] == 1

    def test_token_count_matches_actual_chunk_length(self, chunker):
        text = "a" * 25
        result = chunker.chunk(make_extracted(text))

        for c in result:
            assert c.token_count == len(chunker.encoder.encode(c.text))