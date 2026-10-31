import pytest

from src.catalog.draft.parser import (
    MAX_DESCRIPTION,
    MAX_DRAFT_BODY,
    MAX_NAME,
    DraftParseError,
    parse_draft,
)


def _raw(**kw):
    base = {"skill_name": "Docker Compose", "description": "Run stacks. Use for compose tasks.", "content": "## When to use\nx"}
    base.update(kw)
    return base


def test_valid_draft_is_returned_with_exactly_three_fields():
    assert parse_draft(_raw()) == {
        "skill_name": "Docker Compose",
        "description": "Run stacks. Use for compose tasks.",
        "content": "## When to use\nx",
    }


@pytest.mark.parametrize("raw", [[], "x", None, 5])
def test_non_object_is_rejected(raw):
    with pytest.raises(DraftParseError, match="JSON object"):
        parse_draft(raw)


@pytest.mark.parametrize("field", ["skill_name", "description", "content"])
@pytest.mark.parametrize("bad", [None, 5, ["x"], {"a": 1}])
def test_non_string_fields_are_rejected(field, bad):
    with pytest.raises(DraftParseError, match="must be strings"):
        parse_draft(_raw(**{field: bad}))


@pytest.mark.parametrize("field", ["skill_name", "description", "content"])
def test_missing_field_is_rejected(field):
    raw = _raw()
    del raw[field]
    with pytest.raises(DraftParseError):
        parse_draft(raw)


def test_whitespace_in_name_and_description_is_normalized():
    out = parse_draft(_raw(skill_name="  Docker \n  Compose ", description="a\n\tb   c"))
    assert out["skill_name"] == "Docker Compose" and out["description"] == "a b c"


@pytest.mark.parametrize("name", ["", "   ", "\n"])
def test_blank_name_is_rejected(name):
    with pytest.raises(DraftParseError, match="skill_name"):
        parse_draft(_raw(skill_name=name))


def test_name_and_description_length_boundaries():
    assert parse_draft(_raw(skill_name="n" * MAX_NAME))["skill_name"] == "n" * MAX_NAME
    with pytest.raises(DraftParseError, match="skill_name"):
        parse_draft(_raw(skill_name="n" * (MAX_NAME + 1)))
    assert len(parse_draft(_raw(description="d" * MAX_DESCRIPTION))["description"]) == MAX_DESCRIPTION
    with pytest.raises(DraftParseError, match="description"):
        parse_draft(_raw(description="d" * (MAX_DESCRIPTION + 1)))


def test_length_is_checked_after_whitespace_normalization():
    padded = "n" * MAX_NAME + "      "
    assert parse_draft(_raw(skill_name=padded))["skill_name"] == "n" * MAX_NAME


def test_frontmatter_in_content_is_stripped():
    body = '---\nname: "x"\ndescription: "y"\n---\n## When to use\nz'
    assert parse_draft(_raw(content=body))["content"] == "## When to use\nz"


def test_content_that_is_only_frontmatter_is_rejected():
    with pytest.raises(DraftParseError, match="empty"):
        parse_draft(_raw(content="---\nname: x\n---\n"))


@pytest.mark.parametrize("content", ["", "   \n"])
def test_empty_content_is_rejected(content):
    with pytest.raises(DraftParseError, match="empty"):
        parse_draft(_raw(content=content))


def test_nul_byte_in_content_is_rejected():
    with pytest.raises(DraftParseError, match="NUL"):
        parse_draft(_raw(content="a\x00b"))


def test_content_size_limit():
    assert len(parse_draft(_raw(content="a" * MAX_DRAFT_BODY))["content"]) == MAX_DRAFT_BODY
    with pytest.raises(DraftParseError, match=str(MAX_DRAFT_BODY)):
        parse_draft(_raw(content="a" * (MAX_DRAFT_BODY + 1)))


def test_draft_parse_error_is_a_value_error():
    assert issubclass(DraftParseError, ValueError)
