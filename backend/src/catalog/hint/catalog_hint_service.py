import logging
from collections import Counter

from src.catalog.draft.generator import SkillDraftGenerator
from src.catalog.draft.models import DraftSpec, Snippet
from src.catalog.draft.sources import collect_snippets
from src.catalog.hint.candidate_collector import CandidateCollector
from src.catalog.hint.exceptions import HintClientError, HintParseError, HintValidationError
from src.catalog.hint.models import CatalogCandidate, HintProposal, HintSelection
from src.catalog.hint.parser import parse
from src.catalog.hint.prompts import (
    CANDIDATE_LINE_TEMPLATE,
    CANDIDATE_SECTION_TEMPLATE,
    HINT_SYSTEM_PROMPT,
    HINT_USER_TEMPLATE,
)
from src.rag.retrieval.agentic.exceptions import LLMClientError, LLMParseError, LLMRateLimitError
from src.rag.retrieval.agentic.llm_client import LLMClient
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.document_repo import DocumentRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.schemas.skill_drafts import SkillDraftResult
from src.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

CANDIDATE_WARN_THRESHOLD = 500
MAX_INTENT_CHARS = 2000


class CatalogHintService:

    def __init__(
        self,
        llm_client: LLMClient,
        candidate_collector: CandidateCollector,
        skill_repo: SkillRepository,
        tool_repo: ToolDefinitionRepository,
        pack_repo: KnowledgePackRepository,
        agent_repo: AgentProfileRepository,
        knowledge_service: KnowledgeService | None = None,
        draft_generator: SkillDraftGenerator | None = None,
        document_repo: DocumentRepository | None = None,
        max_retries: int = 1,
    ):
        self.llm_client = llm_client
        self.candidate_collector = candidate_collector
        self.skill_repo = skill_repo
        self.tool_repo = tool_repo
        self.pack_repo = pack_repo
        self.agent_repo = agent_repo
        self.knowledge_service = knowledge_service
        self.draft_generator = draft_generator
        self.document_repo = document_repo
        self.max_retries = max_retries

    async def propose(self, viewer_id: int, intent: str) -> HintProposal:
        if not intent or not intent.strip():
            raise ValueError("intent cannot be empty")
        if len(intent) > MAX_INTENT_CHARS:
            raise ValueError(f"intent must not exceed {MAX_INTENT_CHARS} characters")

        candidates = await self.candidate_collector.collect(viewer_id)
        self._log_candidates(viewer_id, candidates)
        if not candidates:
            return HintProposal(reasoning="Catalog is currently empty.")

        clean_intent = intent.strip()
        prompt = self._build_prompt(clean_intent, candidates)
        selection = await self._ask_with_retry(prompt, candidates)
        proposal, packs = await self._expand_with_packs(viewer_id, selection)

        if packs and self.knowledge_service is not None:
            proposal.generated_skill = await self._generate_grounded_skill(
                intent=clean_intent,
                selection=selection,
                packs=packs,
            )

        return proposal

    def _log_candidates(self, viewer_id: int, candidates: list[CatalogCandidate]) -> None:
        counts = Counter(c.kind.value for c in candidates)
        logger.info(
            "hint_candidates: user=%s total=%d %s", viewer_id, len(candidates), dict(counts)
        )
        if len(candidates) > CANDIDATE_WARN_THRESHOLD:
            logger.warning(
                "hint_candidates_over_threshold: total=%d threshold=%d",
                len(candidates),
                CANDIDATE_WARN_THRESHOLD,
            )

    async def _ask_with_retry(
        self, prompt: str, candidates: list[CatalogCandidate]
    ) -> HintSelection:
        last_error = "unknown error"

        for attempt in range(1 + self.max_retries):
            try:
                raw = await self.llm_client.complete_json(
                    prompt=prompt, system=HINT_SYSTEM_PROMPT
                )
                return parse(raw, candidates)
            except LLMRateLimitError as e:
                raise HintClientError(f"LLM rate limit exhausted: {e}") from e
            except LLMClientError as e:
                raise HintClientError(f"LLM provider error: {e}") from e
            except (LLMParseError, HintParseError, HintValidationError) as e:
                last_error = str(e)
                logger.warning(
                    "Hint attempt %d/%d failed: %s",
                    attempt + 1,
                    1 + self.max_retries,
                    e,
                )
                continue

        raise HintValidationError(f"Invalid hint response after retries: {last_error}")

    def _build_prompt(self, intent: str, candidates: list[CatalogCandidate]) -> str:
        by_kind: dict[str, list[CatalogCandidate]] = {}
        for c in candidates:
            by_kind.setdefault(c.kind.value, []).append(c)

        def section(title: str, kind: str) -> str:
            items = by_kind.get(kind, [])
            if not items:
                return CANDIDATE_SECTION_TEMPLATE.format(title=title, lines="(none available)")
            lines = "\n".join(
                CANDIDATE_LINE_TEMPLATE.format(key=c.key, name=c.name, description=c.description)
                for c in items
            )
            return CANDIDATE_SECTION_TEMPLATE.format(title=title, lines=lines)

        return HINT_USER_TEMPLATE.format(
            intent=intent.strip(),
            profiles_section=section("Agent Profiles", "profile"),
            skills_section=section("Skills", "skill"),
            tools_section=section("Tools", "tool"),
            packs_section=section("Knowledge Packs", "pack"),
        )

    async def _expand(self, viewer_id: int, selection: HintSelection) -> HintProposal:
        proposal, _ = await self._expand_with_packs(viewer_id, selection)
        return proposal

    async def _expand_with_packs(
        self, viewer_id: int, selection: HintSelection
    ) -> tuple[HintProposal, list]:
        profile = None
        inherited_skill_ids: set[int] = set()
        inherited_tool_ids: set[int] = set()

        if selection.profile_key is not None:
            agent = await self.agent_repo.get_active(_entity_id(selection.profile_key))
            if agent is not None:
                profile = {
                    "id": agent.id,
                    "name": agent.agent_name,
                    "description": agent.description,
                }
                base_skills = [
                    {"id": s.id, "name": s.skill_name}
                    for s in agent.skills
                    if getattr(s, "skill_name", None)
                ]
                base_tools = [
                    {"id": t.id, "name": t.tool_name}
                    for t in agent.tools
                    if getattr(t, "tool_name", None)
                ]
                if base_skills:
                    profile["base_skills"] = base_skills
                if base_tools:
                    profile["base_tools"] = base_tools
                inherited_skill_ids = {s.id for s in agent.skills}
                inherited_tool_ids = {t.id for t in agent.tools}

        skill_ids = [_entity_id(k) for k in selection.skill_keys]
        skills = _in_order(
            await self.skill_repo.get_visible_many(skill_ids, viewer_id), skill_ids
        )
        skills = [s for s in skills if s.id not in inherited_skill_ids]

        tool_ids = [_entity_id(k) for k in selection.tool_keys]
        tools = _in_order(await self.tool_repo.get_visible_many(tool_ids, viewer_id), tool_ids)
        tools = [t for t in tools if t.id not in inherited_tool_ids]

        pack_ids = [_entity_id(k) for k in selection.knowledge_pack_keys]
        packs = _in_order(await self.pack_repo.get_active_many(pack_ids), pack_ids)

        proposal = HintProposal(
            agent_profile=profile,
            skills=[{"id": s.id, "name": s.skill_name, "description": s.description} for s in skills],
            tools=[{"id": t.id, "name": t.tool_name, "description": t.description} for t in tools],
            knowledge_packs=[{"id": p.id, "name": p.name, "description": p.description} for p in packs],
            gaps=selection.gaps,
            reasoning=selection.reasoning,
        )
        return proposal, packs

    async def _generate_grounded_skill(
        self,
        intent: str,
        selection: HintSelection,
        packs: list,
    ) -> SkillDraftResult | None:
        queries = list(
            dict.fromkeys(
                q.strip()
                for q in [intent, *selection.search_queries]
                if isinstance(q, str) and q.strip()
            )
        )
        snippets_raw, warnings = await collect_snippets(
            self.knowledge_service,
            queries,
            packs,
            document_repo=self.document_repo,
        )
        if not snippets_raw:
            return None

        snippets = tuple(Snippet.from_dict(s) for s in snippets_raw)
        generator = self.draft_generator or SkillDraftGenerator(
            llm_client=self.llm_client,
            max_retries=self.max_retries,
        )
        try:
            return await generator.generate(
                DraftSpec(
                    intent=intent,
                    snippets=snippets,
                    warnings=tuple(warnings),
                )
            )
        except Exception as exc:
            logger.warning("Hint skill generation failed: %s", exc)
            return None


def _entity_id(key: str) -> int:
    return int(key.rsplit(":", 1)[1])


def _in_order(items: list, ids: list[int]) -> list:
    position = {entity_id: index for index, entity_id in enumerate(ids)}
    return sorted(items, key=lambda item: position.get(item.id, len(ids)))