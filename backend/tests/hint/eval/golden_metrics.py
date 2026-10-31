from __future__ import annotations

from dataclasses import dataclass, field

KINDS = ("skills", "tools", "packs")
SECTIONS = ("profiles",) + KINDS
LANGS = {"en", "uk", "mixed"}


def _names(data: dict, kind: str) -> set[str]:
    return set((data or {}).get(kind) or [])


@dataclass
class CaseOutcome:
    case_id: str
    lang: str
    category: str
    intent: str
    run: int
    status: str  # ok | validation_error | client_error
    predicted_profile: str | None
    predicted: dict[str, set[str]]
    expected: dict[str, set[str]]
    optional: dict[str, set[str]]
    profile_accept: list
    predicted_gaps: list[str] = field(default_factory=list)  # "kind:name" of reported gaps

    @classmethod
    def from_case(
        cls,
        case: dict,
        status: str,
        predicted_profile: str | None,
        predicted: dict[str, set[str]],
        run: int = 0,
        predicted_gaps: list[str] | None = None,
    ) -> "CaseOutcome":
        if status != "ok":
            predicted_profile, predicted = None, {k: set() for k in KINDS}
            predicted_gaps = []
        return cls(
            case_id=case["id"],
            lang=case["lang"],
            category=case["category"],
            intent=case["intent"],
            run=run,
            status=status,
            predicted_profile=predicted_profile,
            predicted={k: set(predicted.get(k, ())) for k in KINDS},
            expected={k: _names(case["expected"], k) for k in KINDS},
            optional={k: _names(case.get("optional", {}), k) for k in KINDS},
            profile_accept=list(case["profile"]),
            predicted_gaps=list(predicted_gaps or []),
        )

    def tp(self, kind: str) -> int:
        return len(self.predicted[kind] & self.expected[kind])

    def fp(self, kind: str) -> int:
        return len(self.predicted[kind] - self.expected[kind] - self.optional[kind])

    def fn(self, kind: str) -> int:
        return len(self.expected[kind] - self.predicted[kind])

    @property
    def profile_ok(self) -> bool:
        return self.status == "ok" and self.predicted_profile in self.profile_accept

    @property
    def exact(self) -> bool:
        return self.profile_ok and all(self.fp(k) == 0 and self.fn(k) == 0 for k in KINDS)

    @property
    def is_empty_case(self) -> bool:
        return all(not self.expected[k] for k in KINDS)

    @property
    def false_gap(self) -> bool:
        """A gap reported although the catalog already covers the request (expected is non-empty)."""
        return not self.is_empty_case and self.status == "ok" and bool(self.predicted_gaps)

    @property
    def clean_empty(self) -> bool:
        return self.is_empty_case and self.status == "ok" and self.profile_ok and all(
            self.fp(k) == 0 for k in KINDS
        )


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    if p is None or r is None:
        f1 = None
    elif p + r == 0:
        f1 = 0.0
    else:
        f1 = 2 * p * r / (p + r)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def _mean(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def summarize_group(outcomes: list[CaseOutcome]) -> dict:
    kinds = {}
    totals = [0, 0, 0]
    for k in KINDS:
        tp = sum(o.tp(k) for o in outcomes)
        fp = sum(o.fp(k) for o in outcomes)
        fn = sum(o.fn(k) for o in outcomes)
        kinds[k] = _prf(tp, fp, fn)
        totals[0] += tp
        totals[1] += fp
        totals[2] += fn
    empty = [o for o in outcomes if o.is_empty_case]
    covered = [o for o in outcomes if not o.is_empty_case and o.status == "ok"]
    return {
        "cases": len(outcomes),
        "overall": _prf(*totals),
        "kinds": kinds,
        "profile_accuracy": _mean([o.profile_ok for o in outcomes]),
        "exact_rate": _mean([o.exact for o in outcomes]),
        "validation_errors": sum(o.status == "validation_error" for o in outcomes),
        "client_errors": sum(o.status == "client_error" for o in outcomes),
        "empty_cases": len(empty),
        "empty_clean_rate": _mean([o.clean_empty for o in empty]),
        "covered_cases": len(covered),
        "false_gap_rate": _mean([o.false_gap for o in covered]),
        "gaps_reported": sum(len(o.predicted_gaps) for o in outcomes),
    }


def _failure(o: CaseOutcome) -> dict:
    return {
        "case_id": o.case_id,
        "run": o.run,
        "intent": o.intent,
        "status": o.status,
        "profile": {"predicted": o.predicted_profile, "accepted": o.profile_accept, "ok": o.profile_ok},
        "gaps": o.predicted_gaps,
        "predicted": {k: sorted(o.predicted[k]) for k in KINDS},
        "missing": {k: sorted(o.expected[k] - o.predicted[k]) for k in KINDS if o.fn(k)},
        "extra": {
            k: sorted(o.predicted[k] - o.expected[k] - o.optional[k]) for k in KINDS if o.fp(k)
        },
    }


def _gap_cases(outcomes: list[CaseOutcome]) -> list[dict]:
    """Per case: how often gaps were reported and which. false=True when the catalog already covers the request."""
    grouped: dict[str, dict] = {}
    for o in outcomes:
        if not o.predicted_gaps:
            continue
        g = grouped.setdefault(
            o.case_id,
            {"case_id": o.case_id, "intent": o.intent, "false": not o.is_empty_case, "runs_with_gaps": 0, "gaps": {}},
        )
        g["runs_with_gaps"] += 1
        for name in o.predicted_gaps:
            g["gaps"][name] = g["gaps"].get(name, 0) + 1
    return sorted(grouped.values(), key=lambda g: (not g["false"], g["case_id"]))


def summarize(outcomes: list[CaseOutcome]) -> dict:
    def group_by(attr: str) -> dict:
        keys = sorted({getattr(o, attr) for o in outcomes})
        return {k: summarize_group([o for o in outcomes if getattr(o, attr) == k]) for k in keys}

    return {
        "all": summarize_group(outcomes),
        "by_lang": group_by("lang"),
        "by_category": group_by("category"),
        "failures": [_failure(o) for o in outcomes if not o.exact],
        "gap_cases": _gap_cases(outcomes),
    }


def _f(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def format_report(summary: dict, verbose: bool = False) -> str:
    a = summary["all"]
    lines = [f"=== ALL: {a['cases']} case-runs ==="]
    for name, m in [("overall", a["overall"])] + list(a["kinds"].items()):
        lines.append(
            f"{name:<8} P={_f(m['precision'])} R={_f(m['recall'])} F1={_f(m['f1'])}"
            f"   (tp={m['tp']} fp={m['fp']} fn={m['fn']})"
        )
    lines.append(f"profile accuracy: {_f(a['profile_accuracy'])}")
    lines.append(f"exact match:      {_f(a['exact_rate'])}")
    lines.append(
        f"errors: validation={a['validation_errors']} client={a['client_errors']}"
        f"   (validation = LLM вигадала ключ і після ретраїв)"
    )
    lines.append(f"no-match cases answered cleanly: {_f(a['empty_clean_rate'])} of {a['empty_cases']}")
    lines.append(
        f"gaps reported: {a['gaps_reported']}   false-gap rate on covered cases: "
        f"{_f(a['false_gap_rate'])} of {a['covered_cases']}"
    )

    for title, groups in (("by lang", summary["by_lang"]), ("by category", summary["by_category"])):
        lines.append("")
        lines.append(f"=== {title} ===")
        lines.append(f"{'':<16}{'n':>4} {'exact':>6} {'prof':>6} {'P':>6} {'R':>6} {'F1':>6}")
        for k, m in groups.items():
            o = m["overall"]
            lines.append(
                f"{k:<16}{m['cases']:>4} {_f(m['exact_rate']):>6} {_f(m['profile_accuracy']):>6}"
                f" {_f(o['precision']):>6} {_f(o['recall']):>6} {_f(o['f1']):>6}"
            )

    fails = summary["failures"]
    lines.append("")
    lines.append(f"=== not exact: {len(fails)} ===")
    for f in fails if verbose else fails[:15]:
        lines.append(f"- {f['case_id']} (run {f['run']}) [{f['status']}] {f['intent'][:70]}")
        if not f["profile"]["ok"]:
            lines.append(f"    profile: got {f['profile']['predicted']!r}, accepted {f['profile']['accepted']}")
        if f["missing"]:
            lines.append(f"    missing: {f['missing']}")
        if f["extra"]:
            lines.append(f"    extra:   {f['extra']}")
        if f["gaps"]:
            lines.append(f"    gaps:    {f['gaps']}")
        if not f["missing"] and not f["extra"] and f["profile"]["ok"]:
            lines.append(f"    (no diff found) predicted: {f['predicted']}")
    if not verbose and len(fails) > 15:
        lines.append(f"... ще {len(fails) - 15} (--verbose щоб побачити всі)")
    gap_cases = summary.get("gap_cases", [])
    if gap_cases:
        lines.append("")
        lines.append("=== gaps reported (FALSE = catalog already covers the request) ===")
        for g in gap_cases:
            tag = "FALSE" if g["false"] else "ok   "
            lines.append(f"- [{tag}] {g['case_id']} in {g['runs_with_gaps']} run(s): {g['intent'][:55]}")
            for name, n in g["gaps"].items():
                lines.append(f"      {n}x {name}")
    return "\n".join(lines)


def validate_golden(catalog: dict, cases: list[dict]) -> list[str]:
    problems: list[str] = []
    names: dict[str, set[str]] = {}
    for section in SECTIONS:
        entries = catalog.get(section)
        if not entries:
            problems.append(f"catalog: section '{section}' is empty or missing")
            continue
        ids = [e["id"] for e in entries]
        ns = [e["name"] for e in entries]
        if len(set(ids)) != len(ids):
            problems.append(f"catalog.{section}: duplicate ids")
        if len(set(ns)) != len(ns):
            problems.append(f"catalog.{section}: duplicate names")
        names[section] = set(ns)

    seen: set[str] = set()
    for c in cases:
        cid = c.get("id", "<no id>")
        if cid in seen:
            problems.append(f"{cid}: duplicate case id")
        seen.add(cid)
        for field in ("lang", "category", "intent", "expected", "profile"):
            if field not in c:
                problems.append(f"{cid}: missing field '{field}'")
        if c.get("lang") not in LANGS:
            problems.append(f"{cid}: lang must be one of {sorted(LANGS)}")
        if not c.get("intent", "").strip():
            problems.append(f"{cid}: empty intent")
        for p in c.get("profile", []):
            if p is not None and p not in names.get("profiles", set()):
                problems.append(f"{cid}: unknown profile '{p}'")
        if not c.get("profile"):
            problems.append(f"{cid}: profile list must not be empty (use [null] for 'none')")
        for k in KINDS:
            exp = _names(c.get("expected", {}), k)
            opt = _names(c.get("optional", {}), k)
            for n in exp | opt:
                if n not in names.get(k, set()):
                    problems.append(f"{cid}: unknown {k[:-1]} '{n}'")
            if exp & opt:
                problems.append(f"{cid}: {k} in both expected and optional: {sorted(exp & opt)}")
    return problems