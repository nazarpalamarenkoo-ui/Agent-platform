import pytest
from pydantic import ValidationError

from src.knowledge.documents_schema.chunk_payload import ChunkPayload


def make_chunk_payload(**overrides):
    defaults = dict(
        document_id=1,
        chunk_index=0,
        text="some chunk text",
        knowledge_pack="python-basics",
        domain="programming",
        language="en",
        framework="unknown",
        version="unknown",
        source_type="pdf",
        tags=["intro", "basics"],
        quality_score=0.85,
        title="Python Basics",
    )
    defaults.update(overrides)
    return ChunkPayload(**defaults)


class TestChunkPayload:

    def test_creates_with_valid_data(self):
        payload = make_chunk_payload()

        assert payload.document_id == 1
        assert payload.chunk_index == 0
        assert payload.text == "some chunk text"
        assert payload.knowledge_pack == "python-basics"
        assert payload.domain == "programming"
        assert payload.language == "en"
        assert payload.framework == "unknown"
        assert payload.version == "unknown"
        assert payload.source_type == "pdf"
        assert payload.tags == ["intro", "basics"]
        assert payload.quality_score == 0.85
        assert payload.title == "Python Basics"

    def test_tags_accepts_empty_list(self):
        payload = make_chunk_payload(tags=[])
        assert payload.tags == []

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            ChunkPayload(
                document_id=1,
                chunk_index=0,
                text="text",
                knowledge_pack="pack",
                domain="domain",
                language="en",
                framework="unknown",
                version="unknown",
                source_type="pdf",
                tags=[],
                title="title",
                # missing quality_score
            )

    def test_document_id_must_be_int_coercible(self):
        with pytest.raises(ValidationError):
            make_chunk_payload(document_id="not-an-int")

    def test_quality_score_accepts_float_boundaries(self):
        low = make_chunk_payload(quality_score=0.0)
        high = make_chunk_payload(quality_score=1.0)

        assert low.quality_score == 0.0
        assert high.quality_score == 1.0

    def test_tags_must_be_a_list(self):
        with pytest.raises(ValidationError):
            make_chunk_payload(tags="not-a-list")

    def test_model_dump_returns_plain_dict(self):
        payload = make_chunk_payload()
        dumped = payload.model_dump()

        assert dumped["document_id"] == 1
        assert dumped["tags"] == ["intro", "basics"]