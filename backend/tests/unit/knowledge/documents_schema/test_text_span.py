import pytest
from pydantic import ValidationError

from src.knowledge.documents_schema.text_span import TextSpan


def make_text_span(**overrides):
    defaults = dict(
        page=1,
        section="Introduction",
        chapter="Chapter 1",
        heading="Overview",
        start_char=0,
        end_char=100,
    )
    defaults.update(overrides)
    return TextSpan(**defaults)


class TestTextSpan:

    def test_creates_with_all_fields(self):
        span = make_text_span()

        assert span.page == 1
        assert span.section == "Introduction"
        assert span.chapter == "Chapter 1"
        assert span.heading == "Overview"
        assert span.start_char == 0
        assert span.end_char == 100

    def test_page_accepts_none(self):
        assert make_text_span(page=None).page is None

    def test_section_accepts_none(self):
        assert make_text_span(section=None).section is None

    def test_chapter_accepts_none(self):
        assert make_text_span(chapter=None).chapter is None

    def test_heading_accepts_none(self):
        assert make_text_span(heading=None).heading is None

    def test_missing_page_raises(self):
        with pytest.raises(ValidationError):
            TextSpan(section=None, chapter=None, heading=None, start_char=0, end_char=10)

    def test_missing_start_char_raises(self):
        with pytest.raises(ValidationError):
            TextSpan(page=None, section=None, chapter=None, heading=None, end_char=10)

    def test_missing_end_char_raises(self):
        with pytest.raises(ValidationError):
            TextSpan(page=None, section=None, chapter=None, heading=None, start_char=0)

    def test_start_char_and_end_char_are_not_cross_validated(self):
        # The schema does not enforce start_char <= end_char.
        span = make_text_span(start_char=50, end_char=10)
        assert span.start_char == 50
        assert span.end_char == 10

    def test_start_char_must_be_int_coercible(self):
        with pytest.raises(ValidationError):
            make_text_span(start_char="not-an-int")