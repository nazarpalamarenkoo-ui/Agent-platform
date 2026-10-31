import asyncio
import logging
import re

from src.config import settings

logger = logging.getLogger(__name__)

MAX_SNIPPETS = 8
MAX_SNIPPET_CHARS = 1500
SEARCH_TIMEOUT = 20.0

HYBRID_LIMIT = 8
HYBRID_TOP_N = 8
HYBRID_K = 60

MIN_SCORE = float(getattr(settings, "DRAFT_MIN_SNIPPET_SCORE", 0.6))

WARN_NO_PACKS = (
    "No knowledge packs selected; the draft is not grounded in the knowledge base."
)
WARN_NOTHING = (
    "The selected knowledge packs have no relevant material for this request."
)
WARN_UNAVAILABLE = (
    "Knowledge search is unavailable; the draft is not grounded in the knowledge base."
)
WARN_PARTIAL = "Part of the knowledge search failed; some material may be missing."

_TAGS = re.compile(r"<\s*/?\s*(?:retrieved_source|user_source)\b[^>]*>", re.I)


async def collect_snippets(
    knowledge_service, queries: list[str], packs: list
) -> tuple[list[dict], list[str]]:
    by_slug = {p.slug: p for p in packs}
    slugs = list(by_slug)

    async def one(query: str):
        return await asyncio.wait_for(
            knowledge_service.search_by_slugs(
                query=query,
                slugs=slugs,
                limit=HYBRID_LIMIT,
                top_n=HYBRID_TOP_N,
                k=HYBRID_K,
            ),
            SEARCH_TIMEOUT,
        )

    outcomes = await asyncio.gather(*(one(q) for q in queries), return_exceptions=True)

    results: list = []
    failed = 0
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            failed += 1
            logger.error("draft search failed: %r", outcome)
            continue
        results.extend(outcome)

    if failed == len(outcomes):
        return [], [WARN_UNAVAILABLE]

    best: dict[str, dict] = {}
    for result in results:
        payload = result.payload if isinstance(result.payload, dict) else {}
        text = _payload_text(payload)
        pack = by_slug.get(payload.get("knowledge_pack"))
        if not text or pack is None:
            continue
        ref = f"{pack.slug}#{payload.get('chunk_index', result.id)}"
        score = float(result.score or 0.0)
        current = best.get(ref)
        if current is None or score > current["score"]:
            best[ref] = {
                "ref": ref,
                "text": text[:MAX_SNIPPET_CHARS],
                "score": score,
                "pack_id": pack.id,
                "pack_slug": pack.slug,
                "pack_name": pack.name,
                "domain_id": pack.domain_id,
            }

    ranked = sorted(best.values(), key=lambda s: s["score"], reverse=True)
    logger.info(
        "draft snippets: queries=%d candidates=%d min_score=%.3f scores=%s",
        len(queries),
        len(ranked),
        MIN_SCORE,
        [round(s["score"], 3) for s in ranked[:MAX_SNIPPETS]],
    )
    strong = [s for s in ranked if s["score"] >= MIN_SCORE][:MAX_SNIPPETS]

    warnings: list[str] = []
    if failed:
        warnings.append(WARN_PARTIAL)
    if not strong:
        warnings.append(WARN_NOTHING)
    return strong, warnings


def _payload_text(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("text") or payload.get("content") or "")


def defang(text: str) -> str:
    previous = None
    current = text or ""
    while previous != current:
        previous = current
        current = _TAGS.sub("", current)
    return current