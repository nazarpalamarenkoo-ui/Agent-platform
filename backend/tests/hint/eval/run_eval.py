import argparse
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # eval -> hint -> tests -> корінь бекенду
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from golden_metrics import CaseOutcome, format_report, summarize, validate_golden  # noqa: E402


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_candidates(catalog: dict):
    from src.catalog.hint.models import CandidateKind, CatalogCandidate

    spec = [
        ("profiles", CandidateKind.PROFILE),
        ("skills", CandidateKind.SKILL),
        ("tools", CandidateKind.TOOL),
        ("packs", CandidateKind.PACK),
    ]
    candidates, key_to_name, name_to_key = [], {}, {}
    for section, kind in spec:
        for e in catalog[section]:
            key = CatalogCandidate.build_key(kind, e["id"])
            candidates.append(
                CatalogCandidate(
                    key=key,
                    kind=kind,
                    entity_id=e["id"],
                    name=e["name"],
                    description=e.get("description") or "",
                )
            )
            key_to_name[key] = e["name"]
            name_to_key[(section, e["name"])] = key
    return candidates, key_to_name, name_to_key


class OracleLLM:

    def __init__(self, cases: list[dict], name_to_key: dict):
        self.by_intent = {c["intent"].strip(): c for c in cases}
        self.name_to_key = name_to_key

    async def complete_json(self, prompt: str, system: str) -> dict:
        intent = prompt.split("\n", 1)[0].removeprefix("User request: ").strip()
        case = self.by_intent[intent]
        profile = next((p for p in case["profile"] if p is not None), None)
        k = lambda section, names: [self.name_to_key[(section, n)] for n in names]  # noqa: E731
        exp = case["expected"]
        return {
            "profile_key": self.name_to_key[("profiles", profile)] if profile else None,
            "skill_keys": k("skills", exp.get("skills", [])),
            "tool_keys": k("tools", exp.get("tools", [])),
            "knowledge_pack_keys": k("packs", exp.get("packs", [])),
            "gaps": [],
            "reasoning": "oracle",
        }


async def evaluate(service, candidates, key_to_name, cases, runs=1, delay=0.0, client_retries=2, backoff=20.0):
    """client_retries: a HintClientError is a rate limit / provider outage, not a model answer,
    so the case is retried after `backoff * attempt` seconds before it is recorded as client_error."""
    from src.catalog.hint.exceptions import HintClientError, HintError

    outcomes: list[CaseOutcome] = []
    for case in cases:
        prompt = service._build_prompt(case["intent"], candidates)
        for run in range(runs):
            status, selection = "ok", None
            for attempt in range(1 + client_retries):
                status, selection = "ok", None
                try:
                    selection = await service._ask_with_retry(prompt, candidates)
                    break
                except HintClientError:
                    status = "client_error"
                    if attempt < client_retries:
                        await asyncio.sleep(backoff * (attempt + 1))
                except HintError:
                    status = "validation_error"
                    break

            profile, predicted, gaps = None, {}, []
            if selection is not None:
                profile = key_to_name[selection.profile_key] if selection.profile_key else None
                predicted = {
                    "skills": {key_to_name[x] for x in selection.skill_keys},
                    "tools": {key_to_name[x] for x in selection.tool_keys},
                    "packs": {key_to_name[x] for x in selection.knowledge_pack_keys},
                }
                gaps = [f"{g.kind.value}:{g.name}" for g in selection.gaps]
            outcomes.append(CaseOutcome.from_case(case, status, profile, predicted, run, gaps))
            if delay:
                await asyncio.sleep(delay)
    return outcomes


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--catalog", default=str(HERE / "catalog.json"))
    p.add_argument("--cases", default=str(HERE / "cases.json"))
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--delay", type=float, default=0.0, help="pause between calls, in seconds (Groq rate limits)")
    p.add_argument("--max-retries", type=int, default=1)
    p.add_argument("--client-retries", type=int, default=2, help="number of case retries on rate limit / provider failure")
    p.add_argument("--backoff", type=float, default=20.0, help="pause between such retries, in seconds (× attempt number)")
    p.add_argument("--lang", choices=["en", "uk", "mixed"])
    p.add_argument("--category")
    p.add_argument("--case", help="id of a single case")
    p.add_argument("--oracle", action="store_true", help="no LLM: sanity-check the test harness")
    p.add_argument("--json", dest="json_out")
    p.add_argument("--fail-under-f1", type=float)
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


async def main() -> int:
    args = parse_args()
    catalog = load_json(args.catalog)
    cases = load_json(args.cases)

    problems = validate_golden(catalog, cases)
    if problems:
        print("Golden files are inconsistent:\n  " + "\n  ".join(problems))
        return 2

    cases = [
        c
        for c in cases
        if (not args.lang or c["lang"] == args.lang)
        and (not args.category or c["category"] == args.category)
        and (not args.case or c["id"] == args.case)
    ]
    if not cases:
        print("No cases match the filters")
        return 2

    candidates, key_to_name, name_to_key = build_candidates(catalog)

    if args.oracle:
        llm = OracleLLM(cases, name_to_key)
    else:
        from src.config import settings
        from src.rag.retrieval.agentic.llm_client import LLMClient

        llm = LLMClient(api_key=settings.MODEL_API_KEY)

    from src.catalog.hint.catalog_hint_service import CatalogHintService

    service = CatalogHintService(
        llm_client=llm,  # type: ignore[arg-type]
        candidate_collector=None,  # type: ignore[arg-type]
        skill_repo=None,  # type: ignore[arg-type]
        tool_repo=None,  # type: ignore[arg-type]
        pack_repo=None,  # type: ignore[arg-type]
        agent_repo=None,  # type: ignore[arg-type]
        max_retries=args.max_retries,
    )

    print(f"catalog: {len(candidates)} entries, {len(cases)} cases x {args.runs} run(s)")
    outcomes = await evaluate(
        service, candidates, key_to_name, cases, args.runs, args.delay, args.client_retries, args.backoff
    )
    summary = summarize(outcomes)
    print(format_report(summary, args.verbose))

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.fail_under_f1 is not None:
        f1 = summary["all"]["overall"]["f1"] or 0.0
        if f1 < args.fail_under_f1:
            print(f"\nFAIL: overall F1 {f1:.2f} < {args.fail_under_f1}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))