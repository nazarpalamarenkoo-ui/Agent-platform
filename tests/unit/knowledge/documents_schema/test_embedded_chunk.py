import pytest
from pydantic import ValidationError

from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk
from src.knowledge.documents_schema.embeddend_chunk import EmbeddedChunk


class TestEmbeddedChunk:

    def test_creates_with_valid_data(self):
        chunk = KnowledgeChunk(chunk_index=0, text="hello", token_count=1)
        embedded = EmbeddedChunk(
            chunk=chunk,
            dense_vector=[0.1, 0.2, 0.3],
            sparse_indices=[1, 5, 9],
            sparse_values=[0.5, 0.25, 0.1],
        )

        assert embedded.chunk == chunk
        assert embedded.dense_vector == [0.1, 0.2, 0.3]
        assert embedded.sparse_indices == [1, 5, 9]
        assert embedded.sparse_values == [0.5, 0.25, 0.1]

    def test_accepts_chunk_as_dict_and_coerces(self):
        embedded = EmbeddedChunk(
            chunk={"chunk_index": 0, "text": "hi", "token_count": 1},
            dense_vector=[],
            sparse_indices=[],
            sparse_values=[],
        )

        assert isinstance(embedded.chunk, KnowledgeChunk)
        assert embedded.chunk.text == "hi"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            EmbeddedChunk(dense_vector=[0.1], sparse_indices=[1], sparse_values=[0.1])

    def test_mismatched_sparse_lengths_are_not_enforced_by_schema(self):
        chunk = KnowledgeChunk(chunk_index=0, text="hi", token_count=1)
        embedded = EmbeddedChunk(
            chunk=chunk,
            dense_vector=[0.1],
            sparse_indices=[1, 2, 3],
            sparse_values=[0.1],
        )
        assert len(embedded.sparse_indices) != len(embedded.sparse_values)