import pytest

from src.knowledge.ingestion.validation.validator import Validator
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk


def make_chunk(text, index=0):
    return KnowledgeChunk(chunk_index=index, text=text, token_count=len(text.split()))


class TestValidate:

    def test_rejects_text_shorter_than_min_length(self):
        validator = Validator(min_lenght=50)
        assert validator.validate(make_chunk("too short")) is False

    def test_accepts_text_meeting_min_length(self):
        validator = Validator(min_lenght=5)
        assert validator.validate(make_chunk("long enough text")) is True

    def test_accepts_text_exactly_at_min_length_boundary(self):
        validator = Validator(min_lenght=10)
        text = "a" * 10
        assert validator.validate(make_chunk(text)) is True

    def test_rejects_text_one_char_below_boundary(self):
        validator = Validator(min_lenght=10)
        text = "a" * 9
        assert validator.validate(make_chunk(text)) is False

    def test_rejects_duplicate_text_on_second_call(self):
        validator = Validator(min_lenght=1)
        chunk_a = make_chunk("identical content here", 0)
        chunk_b = make_chunk("identical content here", 1)

        assert validator.validate(chunk_a) is True
        assert validator.validate(chunk_b) is False

    def test_accepts_different_texts(self):
        validator = Validator(min_lenght=1)
        chunk_a = make_chunk("first unique content", 0)
        chunk_b = make_chunk("second unique content", 1)

        assert validator.validate(chunk_a) is True
        assert validator.validate(chunk_b) is True

    def test_reset_clears_seen_hashes(self):
        validator = Validator(min_lenght=1)
        chunk = make_chunk("repeatable content", 0)

        assert validator.validate(chunk) is True
        assert validator.validate(chunk) is False

        validator.reset()

        assert validator.validate(chunk) is True

    def test_default_min_length(self):
        validator = Validator()
        assert validator.min_lenght == 50

    def test_duplicate_check_is_independent_per_validator_instance(self):
        chunk = make_chunk("shared text between validators", 0)
        validator_one = Validator(min_lenght=1)
        validator_two = Validator(min_lenght=1)

        assert validator_one.validate(chunk) is True
        assert validator_two.validate(chunk) is True