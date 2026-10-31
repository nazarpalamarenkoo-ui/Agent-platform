import logging

from src.catalog.draft.models import DraftSpec
from src.catalog.draft.parser import DraftParseError, parse_draft
from src.catalog.draft.prompts import DRAFT_SYSTEM_PROMPT, DRAFT_USER_TEMPLATE
from src.catalog.draft.sources import MAX_SNIPPET_CHARS, defang
from src.rag.retrieval.agentic.exceptions import LLMParseError
from src.schemas.skill_drafts import SkillDraftResult, UsedPack

logger = logging.getLogger(__name__)

MAX_USER_SOURCE_CHARS = 20_000

UNVERIFIED = (
    "Draft is based on general model knowledge and was not verified against "
    "any source. Review it before saving."
)


class SkillDraftGenerator:
    def __init__(self, llm_client, max_retries: int = 1):
        self.llm_client = llm_client
        self.max_retries = max_retries


    async def generate(self, spec: DraftSpec) -> SkillDraftResult:
        user_text = (spec.source_text or "").strip()[:MAX_USER_SOURCE_CHARS]
        grounded = bool(spec.snippets or user_text)

        warnings = list(spec.warnings)
        if not grounded:
            warnings.append(UNVERIFIED)

        used: dict[str, UsedPack] = {}
        for s in spec.snippets:
            pack = used.setdefault(
                s.pack_slug,
                UsedPack(id=s.pack_id, slug=s.pack_slug, name=s.pack_name or s.pack_slug,
                         domain_id=s.domain_id),
            )
            pack.chunks += 1

        draft = await self._ask(self._build_prompt(spec, user_text))
        return SkillDraftResult(
            **draft,
            grounded=grounded,
            sources=[s.ref for s in spec.snippets] + (["user_source"] if user_text else []),
            used_packs=list(used.values()),
            warnings=warnings,
        )

    async def _ask(self, prompt: str) -> dict:
        last = "unknown error"
        for attempt in range(1 + self.max_retries):
            try:
                raw = await self.llm_client.complete_json(
                    prompt=prompt, system=DRAFT_SYSTEM_PROMPT
                )
                return parse_draft(raw)
            except (LLMParseError, DraftParseError) as e:
                last = str(e)
                logger.warning("Draft attempt %d failed: %s", attempt + 1, e)
        raise ValueError(f"LLM returned an invalid skill draft: {last}")

    @staticmethod
    def _build_prompt(spec: DraftSpec, user_text: str) -> str:
        hints = ""
        if spec.skill_name:
            hints += f"Preferred name: {spec.skill_name}\n"
        if spec.description:
            hints += f"Preferred description: {spec.description}\n"
        if hints:
            hints += "\n"

        blocks = [
            f'<retrieved_source id="{s.ref}">\n{defang(s.text)[:MAX_SNIPPET_CHARS]}\n</retrieved_source>'
            for s in spec.snippets
        ]
        if user_text:
            blocks.append(f"<user_source>\n{defang(user_text)}\n</user_source>")
        sources = "\n\n".join(blocks) if blocks else "(no sources provided)"

        return DRAFT_USER_TEMPLATE.format(
            intent=spec.intent.strip(), hints=hints, sources=sources
        )