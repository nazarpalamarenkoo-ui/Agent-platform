from pydantic import ValidationError

from src.catalog.hint.exceptions import HintValidationError
from src.catalog.hint.models import (
    CandidateKind,
    CatalogCandidate,
    CatalogGap,
    GapKind,
    HintSelection,
)

MAX_SKILLS = 10
MAX_TOOLS = 5
MAX_PACKS = 5
MAX_GAPS = 3

_GAP_TO_CANDIDATE = {
    GapKind.SKILL: CandidateKind.SKILL,
    GapKind.TOOL: CandidateKind.TOOL,
    GapKind.PACK: CandidateKind.PACK,
}


def parse(raw: dict, candidates: list[CatalogCandidate]) -> HintSelection:
    if not isinstance(raw, dict):
        raise HintValidationError("Hint response must be a JSON object")

    data = dict(raw)
    data["gaps"] = _clean_gaps(raw.get("gaps"))

    try:
        selection = HintSelection.model_validate(data)
    except ValidationError as e:
        raise HintValidationError(f"Invalid hint response: {e}") from e

    by_kind: dict[CandidateKind, set[str]] = {kind: set() for kind in CandidateKind}
    for c in candidates:
        by_kind[c.kind].add(c.key)

    unknown: list[str] = []

    if selection.profile_key is not None:
        _check(selection.profile_key, CandidateKind.PROFILE, by_kind, unknown)

    for key in selection.skill_keys:
        _check(key, CandidateKind.SKILL, by_kind, unknown)
    for key in selection.tool_keys:
        _check(key, CandidateKind.TOOL, by_kind, unknown)
    for key in selection.knowledge_pack_keys:
        _check(key, CandidateKind.PACK, by_kind, unknown)

    if unknown:
        raise HintValidationError(
            f"LLM returned keys not present in the candidate list it was "
            f"shown: {sorted(set(unknown))}"
        )

    selection.skill_keys = _dedupe(selection.skill_keys)[:MAX_SKILLS]
    selection.tool_keys = _dedupe(selection.tool_keys)[:MAX_TOOLS]
    selection.knowledge_pack_keys = _dedupe(selection.knowledge_pack_keys)[:MAX_PACKS]
    selection.gaps = _drop_known_gaps(selection.gaps, candidates)

    return selection


def _check(
    key: str,
    expected_kind: CandidateKind,
    by_kind: dict[CandidateKind, set[str]],
    unknown: list[str],
) -> None:
    if not key.startswith(f"{expected_kind.value}:") or key not in by_kind[expected_kind]:
        unknown.append(key)


def _dedupe(keys: list[str]) -> list[str]:
    return list(dict.fromkeys(keys))


def _clean_gaps(value) -> list[dict]:
    if not isinstance(value, list):
        return []

    cleaned: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        name = item.get("name")
        if kind not in {k.value for k in GapKind} or not isinstance(name, str) or not name.strip():
            continue
        description = item.get("description")
        reason = item.get("reason")
        cleaned.append(
            {
                "kind": kind,
                "name": name.strip()[:100],
                "description": description.strip()[:255] if isinstance(description, str) else "",
                "reason": reason.strip()[:300] if isinstance(reason, str) else "",
            }
        )
        if len(cleaned) == MAX_GAPS:
            break
    return cleaned


def _drop_known_gaps(
    gaps: list[CatalogGap], candidates: list[CatalogCandidate]
) -> list[CatalogGap]:
    known: dict[CandidateKind, set[str]] = {kind: set() for kind in CandidateKind}
    for c in candidates:
        known[c.kind].add(c.name.casefold().strip())

    kept: list[CatalogGap] = []
    seen: set[tuple[GapKind, str]] = set()
    for gap in gaps:
        normalized = gap.name.casefold().strip()
        if normalized in known[_GAP_TO_CANDIDATE[gap.kind]]:
            continue
        marker = (gap.kind, normalized)
        if marker in seen:
            continue
        seen.add(marker)
        kept.append(gap)
    return kept