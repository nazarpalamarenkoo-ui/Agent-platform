import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # eval -> draft -> tests -> backend root
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from draft_metrics import DraftOutcome, format_report, summarize, validate_cases  # noqa: E402

DEFAULT_CATALOG = HERE.parent.parent / "hint" / "eval" / "catalog.json"  # packs are shared with the hint eval


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _first(term):
    return term if isinstance(term, str) else term[0]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def build_packs(catalog: dict):
    rows = [SimpleNamespace(id=p["id"], name=p["name"], description=p.get("description") or "") for p in catalog["packs"]]
    by_name = {r.name: r for r in rows}
    return rows, by_name


class FakePackRepo:
    def __init__(self, rows):
        self.rows = rows

    async def list_candidates(self):
        return self.rows


class CountingLLM:
    """Wraps any client: counts generator attempts (calls with the draft system prompt) and
    tallies call errors by type, so rate limits / timeouts are not mistaken for model quality."""

    def __init__(self, inner, draft_system: str):
        self.inner, self.draft_system, self.draft_calls = inner, draft_system, 0
        self.calls = 0
        self.errors: Counter = Counter()

    async def complete_json(self, prompt: str, system: str):
        self.calls += 1
        if system == self.draft_system:
            self.draft_calls += 1
        try:
            return await self.inner.complete_json(prompt=prompt, system=system)
        except asyncio.CancelledError:  # the planner's wait_for cancels us on timeout
            self.errors["timeout"] += 1
            raise
        except Exception as e:
            self.errors[type(e).__name__] += 1
            raise


class OracleLLM:
    """Answers exactly as the golden file expects: validates the stand (parser, metrics), not an LLM."""

    def __init__(self, cases, pack_rows_by_name, plan_system, draft_system):
        self.by_intent = {c["intent"].strip(): c for c in cases}
        self.pack_ids = {n: r.id for n, r in pack_rows_by_name.items()}
        self.plan_system, self.draft_system = plan_system, draft_system

    async def complete_json(self, prompt: str, system: str) -> dict:
        if system == self.plan_system:
            intent = prompt.split("\n", 1)[0].removeprefix("User request: ").strip()
            case = self.by_intent[intent]
            keys = [] if "not needed" in prompt else [f"pack:{self.pack_ids[n]}" for n in case["expected_packs"]]
            terms = [_first(t) for t in case.get("query_terms") or ["general"]]
            return {"pack_keys": keys, "queries": [" ".join(terms)]}
        intent = prompt.split("Skill request:\n", 1)[1].split("\n\n", 1)[0].strip()
        case = self.by_intent[intent]
        facts = "\n".join(f"- `{_first(t)}`" for t in case.get("must_include", []))
        if case["lang"] == "uk":
            body = f"## Коли використовувати\nКоли користувач просить допомогу з цією темою.\n\n## Кроки\n{facts}\n"
            name, desc = "Навичка з оракула", "Допомагає виконати задачу. Використовуйте, коли потрібна ця тема."
        else:
            body = f"## When to use\nWhen the user asks about this topic.\n\n## Steps\n{facts}\n"
            name, desc = "Oracle skill", "Helps with the task. Use when this topic comes up."
        return {"skill_name": name, "description": desc, "content": body}


def build_spec(case, plan, pack_rows_by_name):
    from src.catalog.draft.models import DraftSpec, Snippet

    snippets = []
    for i, s in enumerate(case.get("snippets", [])):
        pack = pack_rows_by_name[s["pack"]]
        slug = slugify(pack.name)
        snippets.append(
            Snippet(ref=f"{slug}#{i}", text=s["text"], score=s.get("score", 0.9), pack_id=pack.id, pack_slug=slug, pack_name=pack.name, domain_id=None)
        )
    return DraftSpec(intent=case["intent"], source_text=case.get("source_text"), snippets=tuple(snippets))


async def evaluate(planner, generator, counting, cases, pack_rows, pack_rows_by_name, stage="both", runs=1, delay=0.0):
    from src.catalog.draft.generator import UNVERIFIED

    id_to_name = {r.id: r.name for r in pack_rows}
    outcomes: list[DraftOutcome] = []
    for case in cases:
        for run in range(runs):
            plan = await planner.plan(case["intent"], pick_packs=case.get("pick_packs", True)) if stage != "generator" else None
            if delay and stage == "both":
                await asyncio.sleep(delay)  # space the planner and generator calls, not only the cases
            predicted = {id_to_name[i] for i in plan.pack_ids} if plan else set(case["expected_packs"])
            queries = plan.queries if plan else list(case.get("query_terms", []))

            spec = build_spec(case, plan, pack_rows_by_name)
            result, status, attempts = None, "skipped", 0
            if stage != "planner":
                before = counting.draft_calls
                try:
                    result, status = await generator.generate(spec), "ok"
                except ValueError:
                    status = "invalid_draft"
                attempts = counting.draft_calls - before
            if delay:
                await asyncio.sleep(delay)

            outcomes.append(
                DraftOutcome(
                    case_id=case["id"], lang=case["lang"], category=case["category"], intent=case["intent"], run=run,
                    planner_expected=set(case["expected_packs"]), planner_optional=set(case.get("optional_packs", [])),
                    planner_predicted=predicted, queries=queries, query_terms=list(case.get("query_terms", [])),
                    gen_status=status, attempts=attempts, expect_grounded=case["expect_grounded"],
                    grounded=result.grounded if result else None, warnings=list(result.warnings) if result else [],
                    sources=list(result.sources) if result else [], expected_sources=[s.ref for s in spec.snippets] + (["user_source"] if (case.get("source_text") or "").strip() else []),
                    content=result.content if result else "", description=result.description if result else "",
                    must_include=list(case.get("must_include", [])), must_not_include=list(case.get("must_not_include", [])),
                    unverified_warning=UNVERIFIED,
                )
            )
    return outcomes


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    p.add_argument("--cases", default=str(HERE / "cases.json"))
    p.add_argument("--stage", choices=["planner", "generator", "both"], default="both")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--delay", type=float, default=0.0, help="pause between cases, in seconds (Groq rate limits)")
    p.add_argument("--max-retries", type=int, default=1)
    p.add_argument("--plan-timeout", type=float, help="override the planner's PLAN_TIMEOUT, in seconds (429 + client retries don't fit in 15 s)")
    p.add_argument("--lang", choices=["en", "uk", "mixed"])
    p.add_argument("--category")
    p.add_argument("--case", help="id of a single case")
    p.add_argument("--oracle", action="store_true", help="no LLM: sanity-check the test harness")
    p.add_argument("--json", dest="json_out")
    p.add_argument("--fail-under-f1", type=float, help="threshold for pack selection F1")
    p.add_argument("--fail-under-pass", type=float, help="threshold for draft pass rate")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


async def main() -> int:
    args = parse_args()
    catalog, cases = load_json(args.catalog), load_json(args.cases)
    problems = validate_cases(catalog, cases)
    if problems:
        print("Golden files are inconsistent:\n  " + "\n  ".join(problems))
        return 2

    cases = [c for c in cases if (not args.lang or c["lang"] == args.lang) and (not args.category or c["category"] == args.category) and (not args.case or c["id"] == args.case)]
    if not cases:
        print("No cases match the filters")
        return 2

    from src.catalog.draft.generator import SkillDraftGenerator
    from src.catalog.draft.planner import PLAN_SYSTEM_PROMPT, DraftPlanner
    from src.catalog.draft.prompts import DRAFT_SYSTEM_PROMPT

    if args.plan_timeout:
        import src.catalog.draft.planner as planner_mod

        planner_mod.PLAN_TIMEOUT = args.plan_timeout

    pack_rows, pack_rows_by_name = build_packs(catalog)
    if args.oracle:
        inner = OracleLLM(cases, pack_rows_by_name, PLAN_SYSTEM_PROMPT, DRAFT_SYSTEM_PROMPT)
    else:
        from src.config import settings
        from src.rag.retrieval.agentic.llm_client import LLMClient

        inner = LLMClient(api_key=settings.MODEL_API_KEY)

    counting = CountingLLM(inner, DRAFT_SYSTEM_PROMPT)
    planner = DraftPlanner(llm_client=counting, pack_repo=FakePackRepo(pack_rows))
    generator = SkillDraftGenerator(llm_client=counting, max_retries=args.max_retries)

    print(f"catalog: {len(pack_rows)} packs, {len(cases)} cases x {args.runs} run(s), stage={args.stage}")
    outcomes = await evaluate(planner, generator, counting, cases, pack_rows, pack_rows_by_name, args.stage, args.runs, args.delay)
    summary = summarize(outcomes)
    summary["llm_calls"] = {"total": counting.calls, "errors": dict(counting.errors)}
    print(format_report(summary, args.verbose))
    if counting.errors:
        print(
            f"\nLLM call errors: {dict(counting.errors)} of {counting.calls} calls "
            "(RateLimit/timeout = harness issue, not the model: increase --delay and/or --plan-timeout)"
        )

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    rc = 0
    if args.fail_under_f1 is not None and args.stage != "generator":
        f1 = summary["all"]["planner"]["f1"] or 0.0
        if f1 < args.fail_under_f1:
            print(f"\nFAIL: planner F1 {f1:.2f} < {args.fail_under_f1}")
            rc = 1
    if args.fail_under_pass is not None and args.stage != "planner":
        pr = summary["all"]["generator"]["pass_rate"] or 0.0
        if pr < args.fail_under_pass:
            print(f"\nFAIL: draft pass rate {pr:.2f} < {args.fail_under_pass}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))