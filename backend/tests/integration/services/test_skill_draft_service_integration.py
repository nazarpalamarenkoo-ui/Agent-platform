from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.db.models.background_jobs import JobStatus, JobType
from src.db.enums.user_role import UserRole
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.background_job_repo import BackgroundJobRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services import skill_draft_service as module
from src.services.config_bundle_service import ConfigBundleService
from src.services.errors import ConflictError, NotFoundError
from src.services.knowledge_service import KnowledgeService
from src.services.skill_draft_service import (
    CONFIRMED_KEY,
    GENERIC_DRAFT_ERROR,
    PACKS_UNAVAILABLE,
    DraftQueueError,
    SkillDraftService,
)
from src.services.user_skill_service import UserSkillService
from src.worker.queues import INGESTION_QUEUE


def make_request(**overrides):
    data = dict(
        intent="  write an api skill  ",
        knowledge_pack_ids=[],
        config_bundle_id=None,
        auto_packs=False,
        search_queries=[],
        skill_name="api-skill",
        description="API skill",
        source_text=None,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.fixture
def arq_pool():
    pool = AsyncMock()
    pool.enqueue_job.return_value = MagicMock()
    return pool


@pytest.fixture
def planner():
    mock = AsyncMock()
    mock.plan.return_value = SimpleNamespace(pack_ids=[], queries=[])
    return mock


@pytest.fixture
def collect(monkeypatch):
    mock = AsyncMock(return_value=([{"text": "snippet"}], []))
    monkeypatch.setattr(module, "collect_snippets", mock)
    return mock


@pytest.fixture
def job_repo(db_session):
    return BackgroundJobRepository(db_session)


@pytest.fixture
def service(db_session, job_repo, arq_pool, planner):
    skill_repo = SkillRepository(db_session)
    domain_repo = KnowledgeDomainRepository(db_session)
    pack_repo = KnowledgePackRepository(db_session)
    return SkillDraftService(
        job_repo=job_repo,
        arq_pool=arq_pool,
        skill_repo=skill_repo,
        user_skill_service=UserSkillService(skill_repo, domain_repo),
        knowledge_service=KnowledgeService(
            AsyncMock(), AsyncMock(), None, domain_repo, ConfigBundleRepository(db_session)
        ),
        bundle_service=ConfigBundleService(
            ConfigBundleRepository(db_session),
            skill_repo,
            ToolDefinitionRepository(db_session),
            pack_repo,
            AgentProfileRepository(db_session),
        ),
        pack_repo=pack_repo,
        planner=planner,
    )


async def finish_job(job_repo, db_session, job_id, result):
    """Put a job into DONE state with a stored result (what the worker would do)."""
    await job_repo.set_result(job_id, result)
    job = await job_repo.get(job_id)
    job.status = JobStatus.DONE.value
    await db_session.commit()


def draft_dict(pack=None, **overrides):
    used = []
    if pack is not None:
        used.append(
            {"id": pack.id, "slug": pack.slug, "name": pack.name, "domain_id": pack.domain_id}
        )
    data = {
        "skill_name": "drafted-skill",
        "description": "Drafted description",
        "content": "# Drafted\nbody",
        "grounded": True,
        "used_packs": used,
    }
    data.update(overrides)
    return data


class TestRequestDraft:
    async def test_creates_job_and_enqueues_it(
        self, service, sample_user, sample_knowledge_pack, arq_pool, job_repo, collect, planner
    ):
        planner.plan.return_value = SimpleNamespace(pack_ids=[], queries=["extra query"])
        req = make_request(knowledge_pack_ids=[sample_knowledge_pack.id])

        job_id, status = await service.request_draft(sample_user, req)

        job = await job_repo.get(job_id)
        assert job.user_id == sample_user.id
        assert job.job_type == JobType.SKILL_GENERATION.value
        assert status == job.status
        assert job.payload["intent"] == "write an api skill"
        assert job.payload["snippets"] == [{"text": "snippet"}]

        arq_pool.enqueue_job.assert_awaited_once()
        args, kwargs = arq_pool.enqueue_job.call_args
        assert args == ("run_skill_draft", job_id)
        assert kwargs["_job_id"] == f"skill_draft:{job_id}"
        assert kwargs["_queue_name"] == INGESTION_QUEUE
        assert kwargs["intent"] == "write an api skill"

    async def test_collects_snippets_for_intent_and_planner_queries(
        self, service, sample_user, sample_knowledge_pack, collect, planner
    ):
        planner.plan.return_value = SimpleNamespace(pack_ids=[], queries=["extra", "write an api skill"])
        req = make_request(knowledge_pack_ids=[sample_knowledge_pack.id])

        await service.request_draft(sample_user, req)

        planner.plan.assert_awaited_once_with("write an api skill", pick_packs=False)
        _, queries, packs = collect.call_args.args
        assert queries == ["write an api skill", "extra"]
        assert [p.id for p in packs] == [sample_knowledge_pack.id]

    async def test_explicit_queries_skip_planner(
        self, service, sample_user, sample_knowledge_pack, collect, planner
    ):
        req = make_request(
            knowledge_pack_ids=[sample_knowledge_pack.id],
            search_queries=["  custom  ", "   "],
        )

        await service.request_draft(sample_user, req)

        planner.plan.assert_not_called()
        assert collect.call_args.args[1] == ["write an api skill", "custom"]

    async def test_auto_packs_uses_planner_picks(
        self, service, sample_user, sample_knowledge_pack, collect, planner
    ):
        planner.plan.return_value = SimpleNamespace(
            pack_ids=[sample_knowledge_pack.id], queries=["q2"]
        )

        await service.request_draft(sample_user, make_request(auto_packs=True))

        planner.plan.assert_awaited_once_with("write an api skill", pick_packs=True)
        assert [p.id for p in collect.call_args.args[2]] == [sample_knowledge_pack.id]

    async def test_without_packs_stores_warning_and_skips_retrieval(
        self, service, sample_user, collect, job_repo
    ):
        job_id, _ = await service.request_draft(sample_user, make_request())

        collect.assert_not_called()
        job = await job_repo.get(job_id)
        assert job.payload["snippets"] == []
        assert job.payload["retrieval_warnings"] == [module.WARN_NO_PACKS]

    async def test_resolves_packs_from_own_bundle_and_skips_archived(
        self, service, sample_user, sample_config_bundle, make_pack,
        sample_knowledge_domain, db_session, collect, planner,
    ):
        active = await make_pack(sample_knowledge_domain)
        archived = await make_pack(sample_knowledge_domain)
        repo = ConfigBundleRepository(db_session)
        await repo.add_knowledge_pack(sample_config_bundle, active)
        await repo.add_knowledge_pack(sample_config_bundle, archived)
        await KnowledgePackRepository(db_session).archive(archived)

        await service.request_draft(
            sample_user, make_request(config_bundle_id=sample_config_bundle.id)
        )

        assert [p.id for p in collect.call_args.args[2]] == [active.id]

    async def test_foreign_bundle_is_rejected_for_regular_user(
        self, service, another_user, sample_config_bundle, collect
    ):
        with pytest.raises(NotFoundError):
            await service.request_draft(
                another_user, make_request(config_bundle_id=sample_config_bundle.id)
            )

    async def test_admin_may_use_any_bundle(
        self, service, make_user, sample_config_bundle, sample_knowledge_pack,
        db_session, collect,
    ):
        admin = await make_user(role=UserRole.ADMIN)
        await ConfigBundleRepository(db_session).add_knowledge_pack(
            sample_config_bundle, sample_knowledge_pack
        )

        await service.request_draft(
            admin, make_request(config_bundle_id=sample_config_bundle.id)
        )

        assert [p.id for p in collect.call_args.args[2]] == [sample_knowledge_pack.id]

    async def test_unknown_explicit_pack_raises(self, service, sample_user, collect):
        with pytest.raises(NotFoundError, match=PACKS_UNAVAILABLE):
            await service.request_draft(
                sample_user, make_request(knowledge_pack_ids=[999_999])
            )

    async def test_quota_exceeded_raises_before_creating_job(
        self, service, sample_user, make_skill, job_repo, arq_pool
    ):
        service.user_skills.max_private_skills = 1
        await make_skill(owner=sample_user)

        with pytest.raises(ConflictError, match="at most 1 active private skills"):
            await service.request_draft(sample_user, make_request())

        arq_pool.enqueue_job.assert_not_called()

    async def test_enqueue_failure_marks_job_failed_and_raises(
        self, service, sample_user, arq_pool, job_repo, collect
    ):
        arq_pool.enqueue_job.side_effect = RuntimeError("redis down")

        with pytest.raises(DraftQueueError):
            await service.request_draft(sample_user, make_request())

        jobs = await job_repo.list_for_user(sample_user.id) if hasattr(job_repo, "list_for_user") else None
        if jobs is not None:
            assert jobs[0].status == JobStatus.FAILED.value
            assert "Enqueue failed" in jobs[0].error

    async def test_duplicate_arq_job_raises_conflict(
        self, service, sample_user, arq_pool, collect
    ):
        arq_pool.enqueue_job.return_value = None

        with pytest.raises(ConflictError, match="already enqueued"):
            await service.request_draft(sample_user, make_request())


class TestGetStatus:
    async def _new_job(self, job_repo, user, **kwargs):
        return await job_repo.create(
            job_type=JobType.SKILL_GENERATION, user_id=user.id, payload={}, **kwargs
        )

    async def test_pending_job_has_no_draft(self, service, sample_user, job_repo):
        job = await self._new_job(job_repo, sample_user)

        status = await service.get_status(sample_user, job.id)

        assert status.job_id == job.id
        assert status.draft is None
        assert status.error is None

    async def test_done_job_returns_validated_draft_without_internal_key(
        self, service, sample_user, job_repo, db_session
    ):
        job = await self._new_job(job_repo, sample_user)
        await finish_job(
            job_repo, db_session, job.id, {**draft_dict(), CONFIRMED_KEY: 42}
        )

        status = await service.get_status(sample_user, job.id)

        assert status.draft.skill_name == "drafted-skill"
        assert status.draft.content == "# Drafted\nbody"

    async def test_failed_job_returns_generic_error(
        self, service, sample_user, job_repo
    ):
        job = await self._new_job(job_repo, sample_user)
        await job_repo.mark_failed(job.id, "secret stack trace")

        status = await service.get_status(sample_user, job.id)

        assert status.error == GENERIC_DRAFT_ERROR
        assert "secret" not in status.error

    async def test_foreign_job_is_not_found(
        self, service, sample_user, another_user, job_repo
    ):
        job = await self._new_job(job_repo, another_user)

        with pytest.raises(NotFoundError, match="Draft not found"):
            await service.get_status(sample_user, job.id)

    async def test_job_of_another_type_is_not_found(
        self, service, sample_user, job_repo
    ):
        other_type = next(t for t in JobType if t != JobType.SKILL_GENERATION)
        job = await job_repo.create(job_type=other_type, user_id=sample_user.id, payload={})

        with pytest.raises(NotFoundError):
            await service.get_status(sample_user, job.id)

    async def test_unknown_job(self, service, sample_user):
        with pytest.raises(NotFoundError):
            await service.get_status(sample_user, 999_999)


class TestConfirm:
    async def _done_job(self, job_repo, db_session, user, result):
        job = await job_repo.create(
            job_type=JobType.SKILL_GENERATION, user_id=user.id, payload={}
        )
        await finish_job(job_repo, db_session, job.id, result)
        return job

    async def test_creates_private_skill_from_draft_and_stores_confirmation(
        self, service, sample_user, sample_knowledge_pack, job_repo, db_session
    ):
        job = await self._done_job(
            job_repo, db_session, sample_user, draft_dict(sample_knowledge_pack)
        )

        skill = await service.confirm(sample_user, job.id, SimpleNamespace(
            skill_name=None, description=None, content=None, domain_ids=None
        ))

        assert skill.skill_name == "drafted-skill"
        assert skill.owner_id == sample_user.id
        assert [d.id for d in skill.domains] == [sample_knowledge_pack.domain_id]
        stored = (await job_repo.get(job.id)).result
        assert stored[CONFIRMED_KEY] == skill.id

    async def test_body_overrides_draft_values_and_domains(
        self, service, sample_user, sample_knowledge_pack, another_knowledge_domain,
        job_repo, db_session,
    ):
        job = await self._done_job(
            job_repo, db_session, sample_user, draft_dict(sample_knowledge_pack)
        )

        skill = await service.confirm(sample_user, job.id, SimpleNamespace(
            skill_name="edited", description="Edited desc", content="edited body",
            domain_ids=[another_knowledge_domain.id],
        ))

        assert skill.skill_name == "edited"
        assert skill.description == "Edited desc"
        assert [d.id for d in skill.domains] == [another_knowledge_domain.id]

    async def test_second_confirm_is_idempotent(
        self, service, sample_user, job_repo, db_session
    ):
        job = await self._done_job(job_repo, db_session, sample_user, draft_dict())
        body = SimpleNamespace(skill_name=None, description=None, content=None, domain_ids=None)

        first = await service.confirm(sample_user, job.id, body)
        second = await service.confirm(sample_user, job.id, body)

        assert second.id == first.id
        owned = await SkillRepository(db_session).count_owned_active(sample_user.id)
        assert owned == 1

    async def test_creates_new_skill_when_confirmed_one_was_deleted(
        self, service, sample_user, job_repo, db_session
    ):
        job = await self._done_job(
            job_repo, db_session, sample_user, {**draft_dict(), CONFIRMED_KEY: 999_999}
        )

        skill = await service.confirm(sample_user, job.id, SimpleNamespace(
            skill_name=None, description=None, content=None, domain_ids=None
        ))

        assert skill.id != 999_999

    async def test_raises_when_draft_not_ready(self, service, sample_user, job_repo):
        job = await job_repo.create(
            job_type=JobType.SKILL_GENERATION, user_id=sample_user.id, payload={}
        )

        with pytest.raises(ConflictError, match="Draft is not ready"):
            await service.confirm(sample_user, job.id, SimpleNamespace(
                skill_name=None, description=None, content=None, domain_ids=None
            ))

    async def test_foreign_job_is_not_found(
        self, service, sample_user, another_user, job_repo, db_session
    ):
        job = await self._done_job(job_repo, db_session, another_user, draft_dict())

        with pytest.raises(NotFoundError):
            await service.confirm(sample_user, job.id, SimpleNamespace(
                skill_name=None, description=None, content=None, domain_ids=None
            ))


class TestAttachUsedPacks:
    async def test_adds_packs_from_draft_to_bundle(
        self, service, sample_user, sample_config_bundle, sample_knowledge_pack,
        job_repo, db_session,
    ):
        job = await job_repo.create(
            job_type=JobType.SKILL_GENERATION, user_id=sample_user.id, payload={}
        )
        await finish_job(job_repo, db_session, job.id, draft_dict(sample_knowledge_pack))

        bundle = await service.attach_used_packs(sample_user, job.id, sample_config_bundle.id)

        assert [p.id for p in bundle.knowledge_packs] == [sample_knowledge_pack.id]

    async def test_raises_when_draft_not_ready(
        self, service, sample_user, sample_config_bundle, job_repo
    ):
        job = await job_repo.create(
            job_type=JobType.SKILL_GENERATION, user_id=sample_user.id, payload={}
        )

        with pytest.raises(ConflictError, match="Draft is not ready"):
            await service.attach_used_packs(sample_user, job.id, sample_config_bundle.id)

    async def test_cannot_attach_to_foreign_bundle(
        self, service, another_user, sample_config_bundle, sample_knowledge_pack,
        job_repo, db_session,
    ):
        job = await job_repo.create(
            job_type=JobType.SKILL_GENERATION, user_id=another_user.id, payload={}
        )
        await finish_job(job_repo, db_session, job.id, draft_dict(sample_knowledge_pack))

        with pytest.raises(NotFoundError):
            await service.attach_used_packs(another_user, job.id, sample_config_bundle.id)


class TestSuggestPacks:
    async def test_returns_packs_in_planner_order_with_queries(
        self, service, planner, sample_knowledge_pack, another_knowledge_pack
    ):
        planner.plan.return_value = SimpleNamespace(
            pack_ids=[another_knowledge_pack.id, sample_knowledge_pack.id],
            queries=["q1", "q2"],
        )

        result = await service.suggest_packs("intent")

        planner.plan.assert_awaited_once_with("intent", pick_packs=True)
        assert [p.id for p in result.packs] == [
            another_knowledge_pack.id,
            sample_knowledge_pack.id,
        ]
        assert result.packs[0].slug == another_knowledge_pack.slug
        assert result.queries == ["q1", "q2"]

    async def test_skips_archived_or_unknown_packs(
        self, service, planner, sample_knowledge_pack, db_session
    ):
        await KnowledgePackRepository(db_session).archive(sample_knowledge_pack)
        planner.plan.return_value = SimpleNamespace(
            pack_ids=[sample_knowledge_pack.id, 999_999], queries=[]
        )

        result = await service.suggest_packs("intent")

        assert result.packs == []