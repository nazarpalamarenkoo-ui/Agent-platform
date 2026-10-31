import pytest

from src.catalog.hint.exceptions import HintValidationError
from src.catalog.hint.models import CandidateKind, CatalogCandidate, GapKind, HintSelection
from src.catalog.hint.parser import MAX_GAPS, MAX_PACKS, MAX_SKILLS, MAX_TOOLS, parse


def _c(kind: CandidateKind, id_: int, name: str | None = None) -> CatalogCandidate:
    return CatalogCandidate(
        key=CatalogCandidate.build_key(kind, id_),
        kind=kind,
        entity_id=id_,
        name=name or f"{kind.value}-{id_}",
        description="d",
    )


CANDIDATES = [
    _c(CandidateKind.PROFILE, 1),
    _c(CandidateKind.PROFILE, 2),
    _c(CandidateKind.SKILL, 1),
    _c(CandidateKind.SKILL, 2, "Docker Basics"),
    _c(CandidateKind.TOOL, 1),
    _c(CandidateKind.PACK, 1),
]


def _raw(**overrides) -> dict:
    base = {
        "profile_key": None,
        "skill_keys": [],
        "tool_keys": [],
        "knowledge_pack_keys": [],
        "gaps": [],
        "reasoning": "r",
    }
    base.update(overrides)
    return base


def test_valid_selection_is_returned():
    sel = parse(
        _raw(
            profile_key="profile:1",
            skill_keys=["skill:1", "skill:2"],
            tool_keys=["tool:1"],
            knowledge_pack_keys=["pack:1"],
        ),
        CANDIDATES,
    )
    assert isinstance(sel, HintSelection)
    assert sel.profile_key == "profile:1"
    assert sel.skill_keys == ["skill:1", "skill:2"]
    assert sel.tool_keys == ["tool:1"]
    assert sel.knowledge_pack_keys == ["pack:1"]


def test_honest_empty_answer_is_valid():
    sel = parse(_raw(), CANDIDATES)
    assert sel.profile_key is None
    assert sel.skill_keys == sel.tool_keys == sel.knowledge_pack_keys == []


def test_unknown_id_with_correct_prefix_is_rejected():
    with pytest.raises(HintValidationError, match="skill:999"):
        parse(_raw(skill_keys=["skill:999"]), CANDIDATES)


def test_key_the_viewer_was_not_shown_is_rejected():
    with pytest.raises(HintValidationError, match="skill:3"):
        parse(_raw(skill_keys=["skill:1", "skill:3"]), CANDIDATES)


@pytest.mark.parametrize(
    "field,key",
    [
        ("skill_keys", "tool:1"),
        ("tool_keys", "skill:1"),
        ("knowledge_pack_keys", "skill:2"),
        ("skill_keys", "pack:1"),
    ],
)
def test_key_of_another_kind_in_a_list_is_rejected(field, key):
    with pytest.raises(HintValidationError):
        parse(_raw(**{field: [key]}), CANDIDATES)


def test_profile_key_must_be_a_profile():
    with pytest.raises(HintValidationError, match="skill:1"):
        parse(_raw(profile_key="skill:1"), CANDIDATES)


@pytest.mark.parametrize("bad", ["Skill:1", "skills:1", "skill-1", "skill:", "1", "", " skill:1"])
def test_malformed_or_wrongly_prefixed_keys_are_rejected(bad):
    with pytest.raises(HintValidationError):
        parse(_raw(skill_keys=[bad]), CANDIDATES)


def test_error_lists_only_the_invalid_keys():
    with pytest.raises(HintValidationError) as exc:
        parse(_raw(skill_keys=["skill:1", "skill:777"], tool_keys=["tool:888"]), CANDIDATES)
    msg = str(exc.value)
    assert "skill:777" in msg and "tool:888" in msg
    assert "skill:1'" not in msg


@pytest.mark.parametrize(
    "raw",
    [
        {"skill_keys": "skill:1"}, 
        {"skill_keys": [1, 2]}, 
        {"profile_key": 5},
        {"knowledge_pack_keys": {"a": 1}},
        {"reasoning": ["x"]},
        [],
        "skill:1",
    ],
)
def test_structurally_invalid_response_is_a_validation_error(raw):
    with pytest.raises(HintValidationError):
        parse(raw, CANDIDATES)


def test_empty_candidate_list_rejects_every_key():
    with pytest.raises(HintValidationError):
        parse(_raw(skill_keys=["skill:1"]), [])

def _gap(**overrides) -> dict:
    base = {"kind": "skill", "name": "Terraform", "description": "IaC", "reason": "not in catalog"}
    base.update(overrides)
    return base


def test_valid_gap_is_kept():
    sel = parse(_raw(gaps=[_gap()]), CANDIDATES)
    assert len(sel.gaps) == 1
    g = sel.gaps[0]
    assert (g.kind, g.name, g.description, g.reason) == (
        GapKind.SKILL, "Terraform", "IaC", "not in catalog",
    )


def test_missing_gaps_field_means_no_gaps():
    raw = _raw()
    del raw["gaps"]
    assert parse(raw, CANDIDATES).gaps == []


@pytest.mark.parametrize("value", ["oops", {"kind": "skill"}, 5, None])
def test_non_list_gaps_are_ignored_not_fatal(value):
    assert parse(_raw(gaps=value), CANDIDATES).gaps == []


@pytest.mark.parametrize(
    "bad",
    [
        "text",
        {"name": "x"},
        {"kind": "profile", "name": "x"},
        {"kind": "skill", "name": "   "},
        {"kind": "skill", "name": 5},
        {"kind": "SKILL", "name": "x"},
    ],
)
def test_malformed_gap_entries_are_dropped_silently(bad):
    sel = parse(_raw(gaps=[bad, _gap(name="Kept")]), CANDIDATES)
    assert [g.name for g in sel.gaps] == ["Kept"]


def test_gap_fields_are_trimmed_and_truncated():
    sel = parse(
        _raw(gaps=[_gap(name="  " + "n" * 150 + "  ", description="d" * 400, reason="r" * 500)]),
        CANDIDATES,
    )
    g = sel.gaps[0]
    assert len(g.name) == 100 and len(g.description) == 255 and len(g.reason) == 300


def test_non_string_description_and_reason_become_empty():
    sel = parse(_raw(gaps=[_gap(description=1, reason=["x"])]), CANDIDATES)
    assert sel.gaps[0].description == "" and sel.gaps[0].reason == ""


def test_gaps_are_capped():
    gaps = [_gap(name=f"gap-{i}") for i in range(MAX_GAPS + 4)]
    assert len(parse(_raw(gaps=gaps), CANDIDATES).gaps) == MAX_GAPS


def test_gap_that_names_an_existing_candidate_of_same_kind_is_dropped():
    # "Docker Basics" exists as a skill -> not a gap; casing and spaces are ignored
    sel = parse(_raw(gaps=[_gap(name="  docker BASICS ")]), CANDIDATES)
    assert sel.gaps == []


def test_gap_with_the_name_of_a_candidate_of_another_kind_is_kept():
    sel = parse(_raw(gaps=[_gap(kind="tool", name="Docker Basics")]), CANDIDATES)
    assert [g.name for g in sel.gaps] == ["Docker Basics"]


def test_duplicate_gaps_are_merged_but_same_name_other_kind_is_kept():
    sel = parse(
        _raw(
            gaps=[
                _gap(name="Terraform"),
                _gap(name="terraform "),
                _gap(kind="tool", name="Terraform"),
            ]
        ),
        CANDIDATES,
    )
    assert [(g.kind, g.name) for g in sel.gaps] == [
        (GapKind.SKILL, "Terraform"),
        (GapKind.TOOL, "Terraform"),
    ]


def test_gap_cap_is_applied_before_filtering_known_ones():
    # documents the current order: first MAX_GAPS cleaned, then known/duplicates removed
    gaps = [_gap(name="Docker Basics")] + [_gap(name=f"g{i}") for i in range(MAX_GAPS + 2)]
    sel = parse(_raw(gaps=gaps), CANDIDATES)
    assert [g.name for g in sel.gaps] == ["g0", "g1"]

def test_duplicate_keys_are_collapsed_keeping_order():
    sel = parse(_raw(skill_keys=["skill:2", "skill:1", "skill:2"]), CANDIDATES)
    assert sel.skill_keys == ["skill:2", "skill:1"]


def _many(kind: CandidateKind, n: int) -> list[CatalogCandidate]:
    return [_c(kind, i) for i in range(1, n + 1)]


def test_lists_are_capped_to_configured_limits():
    cands = (
        _many(CandidateKind.SKILL, MAX_SKILLS + 5)
        + _many(CandidateKind.TOOL, MAX_TOOLS + 5)
        + _many(CandidateKind.PACK, MAX_PACKS + 5)
    )
    sel = parse(
        _raw(
            skill_keys=[c.key for c in cands if c.kind == CandidateKind.SKILL],
            tool_keys=[c.key for c in cands if c.kind == CandidateKind.TOOL],
            knowledge_pack_keys=[c.key for c in cands if c.kind == CandidateKind.PACK],
        ),
        cands,
    )
    assert len(sel.skill_keys) == MAX_SKILLS
    assert len(sel.tool_keys) == MAX_TOOLS
    assert len(sel.knowledge_pack_keys) == MAX_PACKS
    assert sel.skill_keys[0] == "skill:1"


def test_unknown_key_is_still_rejected_even_when_gaps_are_present():
    with pytest.raises(HintValidationError, match="skill:999"):
        parse(_raw(skill_keys=["skill:999"], gaps=[_gap()]), CANDIDATES)


@pytest.mark.xfail(
    strict=True,
    reason="Gap names are free LLM text shown to the user. Under prompt injection the model echoes the "
    "injected keys as gaps ('skill:999'). Fix in parser._clean_gaps: skip names matching "
    r"re.compile(r'^\s*(profile|skill|tool|pack)\s*:\s*\d+', re.I).",
)
@pytest.mark.parametrize("name", ["skill:999", "tool:999", " Skill : 12 ", "pack:3 extra"])
def test_gap_whose_name_is_a_catalog_key_is_dropped(name):
    assert parse(_raw(gaps=[_gap(name=name)]), CANDIDATES).gaps == []