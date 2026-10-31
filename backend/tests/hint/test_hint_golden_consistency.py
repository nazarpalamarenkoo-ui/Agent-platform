import json
import sys
from pathlib import Path

EVAL = Path(__file__).parent / "eval"
sys.path.insert(0, str(EVAL))

from tests.hint.eval.golden_metrics import KINDS, CaseOutcome, summarize, validate_golden  # noqa: E402

CATALOG = json.loads((EVAL / "catalog.json").read_text(encoding="utf-8"))
CASES = json.loads((EVAL / "cases.json").read_text(encoding="utf-8"))


def _outcome(case, status="ok", profile="__expected__", predicted=None):
    if profile == "__expected__":
        profile = next((p for p in case["profile"] if p is not None), None)
    if predicted is None:
        predicted = {k: set(case["expected"][k]) for k in KINDS}
    return CaseOutcome.from_case(case, status, profile, predicted)


def test_golden_files_are_consistent():
    assert validate_golden(CATALOG, CASES) == []


def test_golden_set_covers_required_situations():
    langs = {}
    for c in CASES:
        langs[c["lang"]] = langs.get(c["lang"], 0) + 1
    categories = {c["category"] for c in CASES}

    assert len(CASES) >= 30
    assert langs.get("uk", 0) >= 8, "потрібні українські запити до англомовних записів"
    assert {"exact", "paraphrase", "multi", "no_match", "underspecified", "adversarial"} <= categories


def test_oracle_scores_perfectly():
    s = summarize([_outcome(c) for c in CASES])["all"]
    assert s["exact_rate"] == 1.0
    assert s["profile_accuracy"] == 1.0
    assert s["overall"]["precision"] == 1.0 and s["overall"]["recall"] == 1.0
    assert s["empty_clean_rate"] == 1.0


def test_failed_calls_count_as_missed_not_ignored():
    case = next(c for c in CASES if c["id"] == "en-01")
    s = summarize([_outcome(case, status="validation_error")])["all"]
    assert s["validation_errors"] == 1
    assert s["overall"]["recall"] == 0.0
    assert s["exact_rate"] == 0.0


def test_extra_pick_lowers_precision_but_optional_does_not():
    case = next(c for c in CASES if c["id"] == "en-01")  # optional skill: System Design

    with_optional = {k: set(case["expected"][k]) for k in KINDS}
    with_optional["skills"].add("System Design")
    assert summarize([_outcome(case, predicted=with_optional)])["all"]["exact_rate"] == 1.0

    with_wrong = {k: set(case["expected"][k]) for k in KINDS}
    with_wrong["skills"].add("Prompt Engineering")
    s = summarize([_outcome(case, predicted=with_wrong)])["all"]
    assert s["overall"]["precision"] < 1.0 and s["exact_rate"] == 0.0


def test_picking_anything_on_a_no_match_case_is_not_clean():
    case = next(c for c in CASES if c["id"] == "none-01")
    predicted = {k: set() for k in KINDS}
    predicted["skills"].add("Technical Writing")
    s = summarize([_outcome(case, predicted=predicted)])["all"]
    assert s["empty_clean_rate"] == 0.0

def test_reported_gap_on_a_covered_case_is_a_false_gap_but_not_on_an_uncovered_one():
    covered = next(c for c in CASES if c["id"] == "en-01")
    o = _outcome(covered)
    o.predicted_gaps = ["skill:Terraform"]
    s = summarize([o])["all"]
    assert s["false_gap_rate"] == 1.0 and s["gaps_reported"] == 1
    # gaps alone do not change precision/recall/exact
    assert s["exact_rate"] == 1.0

    uncovered = next(c for c in CASES if c["id"] == "none-01")
    o = _outcome(uncovered)
    o.predicted_gaps = ["skill:Cooking"]
    s = summarize([o])["all"]
    assert s["covered_cases"] == 0 and s["false_gap_rate"] is None
    assert s["empty_clean_rate"] == 1.0


def test_failed_call_reports_no_gaps():
    case = next(c for c in CASES if c["id"] == "en-01")
    o = CaseOutcome.from_case(case, "validation_error", None, {}, predicted_gaps=["skill:x"])
    assert o.predicted_gaps == [] and summarize([o])["all"]["gaps_reported"] == 0


def test_gap_cases_lists_false_gaps_first_and_counts_runs():
    covered = next(c for c in CASES if c["id"] == "en-01")
    uncovered = next(c for c in CASES if c["id"] == "none-01")
    outs = []
    for case, gaps in [(uncovered, ["skill:Cooking"]), (covered, ["skill:Terraform"]), (covered, ["skill:Terraform", "tool:Helm"]), (covered, [])]:
        o = _outcome(case)
        o.predicted_gaps = gaps
        outs.append(o)
    s = summarize(outs)
    assert [g["case_id"] for g in s["gap_cases"]] == ["en-01", "none-01"]
    first = s["gap_cases"][0]
    assert first["false"] is True and first["runs_with_gaps"] == 2
    assert first["gaps"] == {"skill:Terraform": 2, "tool:Helm": 1}
    assert s["gap_cases"][1]["false"] is False

class _FlakyService:
    def __init__(self, failures, final=None):
        from src.catalog.hint.models import HintSelection

        self.failures, self.calls = failures, 0
        self.final = final or HintSelection()

    def _build_prompt(self, intent, candidates):
        return intent

    async def _ask_with_retry(self, prompt, candidates):
        from src.catalog.hint.exceptions import HintClientError

        self.calls += 1
        if self.calls <= self.failures:
            raise HintClientError("rate limit")
        return self.final


def _evaluate(service, **kw):
    import asyncio
    from tests.hint.eval import run_eval

    case = next(c for c in CASES if c["id"] == "none-01")
    return asyncio.run(run_eval.evaluate(service, [], {}, [case], backoff=0.0, **kw))


def test_client_error_is_retried_and_then_scored_normally():
    svc = _FlakyService(failures=2)
    (o,) = _evaluate(svc, client_retries=2)
    assert svc.calls == 3 and o.status == "ok"


def test_client_error_is_recorded_only_after_retries_are_exhausted():
    svc = _FlakyService(failures=99)
    (o,) = _evaluate(svc, client_retries=2)
    assert svc.calls == 3 and o.status == "client_error"


def test_client_retries_zero_keeps_the_old_behaviour():
    svc = _FlakyService(failures=99)
    (o,) = _evaluate(svc, client_retries=0)
    assert svc.calls == 1 and o.status == "client_error"