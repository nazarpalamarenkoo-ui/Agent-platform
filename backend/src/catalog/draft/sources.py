import asyncio
import logging
import re

from src.config import settings
from src.repositories.document_repo import format_document_source

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
    knowledge_service, queries: list[str], packs: list, document_repo=None
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
            entry = {
                "ref": ref,
                "text": text[:MAX_SNIPPET_CHARS],
                "score": score,
                "pack_id": pack.id,
                "pack_slug": pack.slug,
                "pack_name": pack.name,
                "domain_id": getattr(pack, "domain_id", None),
            }
            doc_id = _coerce_int(payload.get("document_id"))
            if doc_id is not None:
                entry["document_id"] = doc_id
            payload_source = format_document_source(payload.get("source"))
            if payload_source:
                entry["source"] = payload_source
            payload_type = payload.get("source_type") or payload.get("document_type")
            if isinstance(payload_type, str) and payload_type.strip():
                entry["document_type"] = payload_type.strip()
            best[ref] = entry

    ranked = sorted(best.values(), key=lambda s: s["score"], reverse=True)
    logger.info(
        "draft snippets: queries=%d candidates=%d min_score=%.3f scores=%s",
        len(queries),
        len(ranked),
        MIN_SCORE,
        [round(s["score"], 3) for s in ranked[:MAX_SNIPPETS]],
    )
    strong = [s for s in ranked if s["score"] >= MIN_SCORE][:MAX_SNIPPETS]

    doc_repo = (
        document_repo
        if document_repo is not None
        else (
            knowledge_service.__dict__.get("document_repo")
            if hasattr(knowledge_service, "__dict__")
            else None
        )
    )
    if doc_repo is not None and strong:
        await _enrich_document_sources(strong, doc_repo)

    warnings: list[str] = []
    if failed:
        warnings.append(WARN_PARTIAL)
    if not strong:
        warnings.append(WARN_NOTHING)
    return strong, warnings


async def _enrich_document_sources(snippets: list[dict], doc_repo) -> None:
    doc_ids = [
        s["document_id"]
        for s in snippets
        if isinstance(s.get("document_id"), int)
    ]
    if not doc_ids:
        return
    try:
        docs = await doc_repo.get_by_ids(doc_ids)
    except Exception:
        logger.warning("Failed to resolve document sources for %s", doc_ids, exc_info=True)
        return

    by_id = {d.id: d for d in (docs or []) if getattr(d, "id", None) is not None}
    for s in snippets:
        doc = by_id.get(s.get("document_id"))
        if doc is None:
            continue
        clean_source = format_document_source(getattr(doc, "source", None))
        if clean_source:
            s["source"] = clean_source
        raw_type = getattr(doc, "document_type", None)
        if raw_type is not None:
            type_val = getattr(raw_type, "value", str(raw_type))
            if type_val:
                s["document_type"] = str(type_val)


def _coerce_int(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


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