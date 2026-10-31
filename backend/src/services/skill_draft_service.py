import logging

from arq.connections import ArqRedis
from src.catalog.draft.planner import DraftPlanner
from src.schemas.skill_drafts import PackRef, PackSuggestion
from src.catalog.draft.sources import WARN_NO_PACKS, collect_snippets
from src.db.models.background_jobs import JobStatus, JobType
from src.db.models.skills import Skill
from src.db.models.users import User
from src.repositories.background_job_repo import BackgroundJobRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.schemas.skill_drafts import (
    SkillDraftConfirm,
    SkillDraftRequest,
    SkillDraftResult,
    SkillDraftStatus,
)
from src.services.config_bundle_service import ConfigBundleService
from src.services.errors import ConflictError, NotFoundError
from src.services.knowledge_service import KnowledgeService
from src.services.user_skill_service import UserSkillService
from src.worker.queues import INGESTION_QUEUE

logger = logging.getLogger(__name__)

GENERIC_DRAFT_ERROR = "Draft generation failed, try again later"
CONFIRMED_KEY = "confirmed_skill_id"
PACKS_UNAVAILABLE = "One or more selected knowledge packs are unavailable"

class DraftQueueError(Exception):
    pass

class SkillDraftService:

    def __init__(
        self,
        job_repo: BackgroundJobRepository,
        arq_pool: ArqRedis,
        skill_repo: SkillRepository,
        user_skill_service: UserSkillService,
        knowledge_service: KnowledgeService,
        bundle_service: ConfigBundleService,
        pack_repo: KnowledgePackRepository,
        planner: DraftPlanner
    ):
        self.job_repo = job_repo
        self.arq_pool = arq_pool
        self.skill_repo = skill_repo
        self.user_skills = user_skill_service
        self.knowledge = knowledge_service
        self.bundles = bundle_service
        self.pack_repo = pack_repo
        self.planner = planner
        
    async def _resolve_packs(self, actor: User, req: SkillDraftRequest) -> list:
        packs: dict[int, object] = {}

        explicit_ids = list(dict.fromkeys(req.knowledge_pack_ids))
        if explicit_ids:
            found = await self.pack_repo.get_active_many(explicit_ids)
            if len(found) != len(explicit_ids):
                raise NotFoundError(PACKS_UNAVAILABLE)
            packs.update({p.id: p for p in found})

        if req.config_bundle_id is not None:
            if not actor.is_admin:
                await self.bundles.get_bundle(req.config_bundle_id, actor.id)
            for pack in await self.pack_repo.list_for_bundle(req.config_bundle_id):
                if pack.archived_at is None:
                    packs.setdefault(pack.id, pack)

        return list(packs.values())
    
    async def request_draft(self, actor: User, req: SkillDraftRequest) -> tuple[int, str]:
        limit = self.user_skills.max_private_skills
        if await self.skill_repo.count_owned_active(actor.id) >= limit:
            raise ConflictError(f"You can have at most {limit} active private skills")

        intent = req.intent.strip()
        packs = await self._resolve_packs(actor, req)
        queries = [intent] + [q.strip() for q in req.search_queries if q.strip()]

        need_pick = req.auto_packs and not packs
        need_queries = bool(packs) and not req.search_queries
        if need_pick or need_queries:
            plan = await self.planner.plan(intent, pick_packs=need_pick)
            if need_pick and plan.pack_ids:
                packs = await self.pack_repo.get_active_many(plan.pack_ids)
            queries += plan.queries
        queries = list(dict.fromkeys(queries))

        snippets: list[dict] = []
        warnings: list[str] = []
        if packs:
            snippets, warnings = await collect_snippets(self.knowledge, queries, packs)
        else:
            warnings = [WARN_NO_PACKS]

        payload = {
            "intent": intent,
            "skill_name": req.skill_name,
            "description": req.description,
            "source_text": req.source_text,
            "snippets": snippets,
            "retrieval_warnings": warnings,
        }
        job = await self.job_repo.create(
            job_type=JobType.SKILL_GENERATION, user_id=actor.id, payload=payload
        )
        try:
            enqueued = await self.arq_pool.enqueue_job(
                "run_skill_draft",
                job.id,
                **payload,
                _job_id=f"skill_draft:{job.id}",
                _queue_name=INGESTION_QUEUE,
            )
        except Exception as exc:
            logger.exception("Failed to enqueue draft job %d", job.id)
            await self.job_repo.mark_failed(job.id, f"Enqueue failed: {exc}")
            raise DraftQueueError("Queue unavailable") from exc
        if enqueued is None:
            await self.job_repo.mark_failed(job.id, "Duplicate arq job id")
            raise ConflictError("Draft job already enqueued")
        return job.id, job.status

    async def get_status(self, actor: User, job_id: int) -> SkillDraftStatus:
        job = await self._get_owned_job(actor, job_id)
        draft = None
        if job.status == JobStatus.DONE.value and job.result:
            draft_data, _ = self._split_result(job.result)
            draft = SkillDraftResult.model_validate(draft_data)
        return SkillDraftStatus(
            job_id=job.id,
            status=job.status,
            error=GENERIC_DRAFT_ERROR if job.error else None,
            draft=draft,
        )
        
    async def attach_used_packs(self, actor: User, job_id: int, bundle_id: int):
        job = await self._get_owned_job(actor, job_id)
        if job.status != JobStatus.DONE.value or not job.result:
            raise ConflictError("Draft is not ready")
        draft_data, _ = self._split_result(job.result)
        draft = SkillDraftResult.model_validate(draft_data)
        pack_ids = [p.id for p in draft.used_packs if p.id is not None]
        return await self.bundles.add_to_bundle(
            bundle_id, actor.id, knowledge_pack_ids=pack_ids
        )
        
    async def confirm(self, actor: User, job_id: int, body: SkillDraftConfirm) -> Skill:
        job = await self._get_owned_job(actor, job_id)
        if job.status != JobStatus.DONE.value or not job.result:
            raise ConflictError("Draft is not ready")

        draft_data, confirmed_id = self._split_result(job.result)
        if confirmed_id is not None:
            try:
                return await self.user_skills.get_skill(actor, confirmed_id)
            except NotFoundError:
                pass

        draft = SkillDraftResult.model_validate(draft_data)
        domain_ids = body.domain_ids or sorted(
            {p.domain_id for p in draft.used_packs if p.domain_id is not None}
        )
        skill = await self.user_skills.create_skill(
            actor,
            body.skill_name or draft.skill_name,
            body.description or draft.description,
            body.content or draft.content,
            domain_ids,
        )
        await self.job_repo.set_result(job.id, {**draft_data, CONFIRMED_KEY: skill.id})
        return skill
    
    async def suggest_packs(self, intent: str) -> PackSuggestion:
        plan = await self.planner.plan(intent, pick_packs=True)
        packs = await self.pack_repo.get_active_many(plan.pack_ids)
        order = {pid: i for i, pid in enumerate(plan.pack_ids)}
        packs.sort(key=lambda p: order.get(p.id, 99))
        return PackSuggestion(
            packs=[PackRef(id=p.id, slug=p.slug, name=p.name, description=p.description)
                   for p in packs],
            queries=plan.queries,
        )
        
    @staticmethod
    def _split_result(result: dict) -> tuple[dict, int | None]:
        data = dict(result)
        confirmed = data.pop(CONFIRMED_KEY, None)
        return data, confirmed

    async def _get_owned_job(self, actor: User, job_id: int):
        job = await self.job_repo.get(job_id)
        if (
            job is None
            or job.user_id != actor.id
            or job.job_type != JobType.SKILL_GENERATION.value
        ):
            raise NotFoundError("Draft not found")
        return job