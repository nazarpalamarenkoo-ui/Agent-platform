import pytest
from pydantic import ValidationError

from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk


class TestKnowledgeChunk:

    def test_creates_with_required_fields(self):
        chunk = KnowledgeChunk(chunk_index=0, text="some text", token_count=3)

        assert chunk.document_id is None
        assert chunk.chunk_index == 0
        assert chunk.text == "some text"
        assert chunk.token_count == 3
        assert chunk.metadata == {}

    def test_creates_with_document_id_and_metadata(self):
        chunk = KnowledgeChunk(
            document_id=42,
            chunk_index=1,
            text="chunk text",
            token_count=10,
            metadata={"source": "doc.pdf", "page": 2},
        )

        assert chunk.document_id == 42
        assert chunk.metadata == {"source": "doc.pdf", "page": 2}

    def test_metadata_default_not_shared_between_instances(self):
        first = KnowledgeChunk(chunk_index=0, text="a", token_count=1)
        second = KnowledgeChunk(chunk_index=1, text="b", token_count=1)

        first.metadata["x"] = 1

        assert first.metadata == {"x": 1}
        assert second.metadata == {}

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            KnowledgeChunk(chunk_index=0, token_count=3)

    def test_model_copy_creates_independent_instance(self):
        chunk = KnowledgeChunk(chunk_index=0, text="original", token_count=2)
        copy = chunk.model_copy(update={"text": "changed"})

        assert chunk.text == "original"
        assert copy.text == "changed"
        assert copy.chunk_index == chunk.chunk_index