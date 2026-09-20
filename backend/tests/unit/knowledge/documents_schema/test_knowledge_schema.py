from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.knowledge.documents_schema.knowledge_document import KnowledgeDocument


def make_knowledge_document(**overrides):
    defaults = dict(
        title="Designing Data-Intensive Applications",
        source="https://example.com/book.pdf",
        source_type="pdf",
        topic="distributed systems",
        summary="A book about data systems.",
        text="Full extracted text...",
        content_hash="a" * 64,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return KnowledgeDocument(**defaults)


class TestKnowledgeDocument:

    def test_creates_with_required_fields(self):
        doc = make_knowledge_document()

        assert doc.document_id is None
        assert doc.concepts == []
        assert doc.technologies == []
        assert doc.tags == []
        assert doc.page is None
        assert doc.section is None

    def test_creates_with_optional_fields(self):
        doc = make_knowledge_document(
            document_id=1,
            concepts=["CAP theorem"],
            technologies=["Kafka"],
            tags=["backend"],
            page=12,
            section="Chapter 2",
        )

        assert doc.document_id == 1
        assert doc.concepts == ["CAP theorem"]
        assert doc.technologies == ["Kafka"]
        assert doc.tags == ["backend"]
        assert doc.page == 12
        assert doc.section == "Chapter 2"

    def test_list_defaults_are_independent_across_instances(self):
        first = make_knowledge_document()
        second = make_knowledge_document()

        first.concepts.append("sharding")

        assert first.concepts == ["sharding"]
        assert second.concepts == []

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            KnowledgeDocument(
                source="https://example.com",
                source_type="pdf",
                topic="topic",
                summary="summary",
                text="text",
                content_hash="a" * 64,
                created_at=datetime.now(timezone.utc),
            )