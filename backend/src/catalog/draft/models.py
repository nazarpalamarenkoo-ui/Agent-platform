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
    document_id: int | None = None
    source: str = ""
    document_type: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Snippet":
        return cls(
            ref=data["ref"],
            text=data["text"],
            score=data.get("score", 0.0),
            pack_id=data.get("pack_id"),
            pack_slug=data.get("pack_slug", ""),
            pack_name=data.get("pack_name", ""),
            domain_id=data.get("domain_id"),
            document_id=data.get("document_id"),
            source=data.get("source", ""),
            document_type=data.get("document_type", ""),
        )


@dataclass(frozen=True)
class DraftSpec:
    intent: str
    skill_name: str | None = None
    description: str | None = None
    source_text: str | None = None
    snippets: tuple[Snippet, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)