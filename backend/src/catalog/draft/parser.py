from src.catalog.hint.skill_markdown import clean_skill_body

MAX_NAME = 100
MAX_DESCRIPTION = 255
MAX_DRAFT_BODY = 50_000


class DraftParseError(ValueError):
    pass


def parse_draft(raw) -> dict:
    if not isinstance(raw, dict):
        raise DraftParseError("Draft response must be a JSON object")

    name = raw.get("skill_name")
    description = raw.get("description")
    content = raw.get("content")
    if (
        not isinstance(name, str)
        or not isinstance(description, str)
        or not isinstance(content, str)
    ):
        raise DraftParseError("skill_name, description and content must be strings")

    name = " ".join(name.split())
    description = " ".join(description.split())
    if not name or len(name) > MAX_NAME:
        raise DraftParseError(f"skill_name must be 1-{MAX_NAME} characters")
    if not description or len(description) > MAX_DESCRIPTION:
        raise DraftParseError(f"description must be 1-{MAX_DESCRIPTION} characters")
    try:
        body = clean_skill_body(content, MAX_DRAFT_BODY)
    except ValueError as e:
        raise DraftParseError(str(e)) from e

    return {"skill_name": name, "description": description, "content": body}