import hashlib
import json
import re
from typing import Iterable

MAX_DIR_NAME_LENGTH = 64
MAX_BODY_CHARS = 50_000

_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def skill_dir_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:MAX_DIR_NAME_LENGTH].strip("-") or "skill"


def assign_skill_dirs(skills: Iterable[tuple[int, str]]) -> dict[int, str]:
    used: set[str] = set()
    result: dict[int, str] = {}
    for skill_id, name in skills:
        base = skill_dir_name(name)
        directory = base
        attempt = 1
        while directory in used:
            directory = f"{base}-{skill_id}" if attempt == 1 else f"{base}-{skill_id}-{attempt}"
            attempt += 1
        used.add(directory)
        result[skill_id] = directory
    return result


def clean_skill_body(content: str, max_chars: int = MAX_BODY_CHARS) -> str:
    text = strip_frontmatter(content or "").strip()
    if "\x00" in text:
        raise ValueError("Skill content must not contain NUL characters")
    if not text:
        raise ValueError("Skill content must not be empty")
    if len(text) > max_chars:
        raise ValueError(f"Skill content must not exceed {max_chars} characters")
    return text


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER.match(text or "")
    if match is None:
        return {}, text or ""
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "\t", "#")):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = _unquote(value.strip())
    return meta, text[match.end():]


def strip_frontmatter(text: str) -> str:
    return split_frontmatter(text)[1]


def render_skill_md(name: str, description: str, body: str) -> str:
    clean_description = " ".join((description or "").split())
    header = "\n".join(
        [
            "---",
            f"name: {json.dumps(skill_dir_name(name))}",
            f"description: {json.dumps(clean_description, ensure_ascii=False)}",
            "---",
            "",
        ]
    )
    return header + strip_frontmatter(body or "").strip() + "\n"


def skill_file_hash(name: str, description: str, body: str) -> str:
    return hashlib.sha256(render_skill_md(name, description, body).encode("utf-8")).hexdigest()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        try:
            parsed = json.loads(value)
            if isinstance(parsed, str):
                return parsed
        except ValueError:
            pass
        return value[1:-1]
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value