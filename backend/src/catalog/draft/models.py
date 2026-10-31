from dataclasses import dataclass, field


@dataclass(frozen=True)
class Snippet:
    ref: str
    text: str
    score: float = 0.0
    pack_id: int | None = None
    pack_slug: str = ""
    pack_name: str = ""
    domain_id: int | None = None


@dataclass(frozen=True)
class DraftSpec:
    intent: str
    skill_name: str | None = None
    description: str | None = None
    source_text: str | None = None
    snippets: tuple[Snippet, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)