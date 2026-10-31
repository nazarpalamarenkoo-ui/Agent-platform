from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.db.models.background_jobs import JobStatus, JobType
from src.services import skill_draft_service as mod
from src.services.errors import ConflictError, NotFoundError
from src.services.skill_draft_service import (
    CONFIRMED_KEY,
    GENERIC_DRAFT_ERROR,
    PACKS_UNAVAILABLE,
    DraftQueueError,
    SkillDraftService,
)
from src.worker.queues import INGESTION_QUEUE

ACTOR = SimpleNamespace(id=1, is_admin=False)
ADMIN = SimpleNamespace(id=2, is_admin=True)
DONE = JobStatus.DONE.value


def pack(id, domain_id=None, archived_at=None, slug=None):
    return SimpleNamespace(
        id=id, domain_id=domain_id, archived_at=archived_at,
        slug=slug or f"p{id}", name=f"Pack {id}", description="d",
    )


def make_req(**kw):
    data = dict(
        intent="  learn sql  ", knowledge_pack_ids=[], config_bundle_id=None, auto_packs=False,
        search_queries=[], skill_name=None, description=None, source_text=None,
    )
    data.update(kw)
    return SimpleNamespace(**data)


def make_job(status=DONE, result=None, error=None, user_id=1, job_type=JobType.SKILL_GENERATION.value, id=10):
    return SimpleNamespace(id=id, status=status, result=result, error=error, user_id=user_id, job_type=job_type)


@pytest.fixture(autouse=True)
def fake_schemas(monkeypatch):
    class FakeResult:
        @staticmethod
        def model_validate(data):
            return SimpleNamespace(**data)

    monkeypatch.setattr(mod, "SkillDraftResult", FakeResult)
    monkeypatch.setattr(mod, "SkillDraftStatus", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(mod, "PackRef", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(mod, "PackSuggestion", lambda **kw: SimpleNamespace(**kw))


@pytest.fixture
def collect(monkeypatch):
    mock = AsyncMock(return_value=([{"text": "snippet"}], ["warn"]))
    monkeypatch.setattr(mod, "collect_snippets", mock)
    return mock


@pytest.fixture
def repos():
    job_repo = AsyncMock()
    job_repo.create.return_value = SimpleNamespace(id=10, status="pending")
    arq_pool = AsyncMock()
    arq_pool.enqueue_job.return_value = object()
    skill_repo = AsyncMock()
    skill_repo.count_owned_active.return_value = 0
    user_skills = AsyncMock()
    user_skills.max_private_skills = 5
    pack_repo = AsyncMock()
    pack_repo.get_active_many.return_value = []
    pack_repo.list_for_bundle.return_value = []
    planner = AsyncMock()
    planner.plan.return_value = SimpleNamespace(pack_ids=[], queries=[])
    return SimpleNamespace(
        job=job_repo, arq=arq_pool, skill=skill_repo, user_skills=user_skills,
        knowledge=AsyncMock(), bundles=AsyncMock(), pack=pack_repo, planner=planner,
    )


@pytest.fixture
def service(repos):
    return SkillDraftService(
        repos.job, repos.arq, repos.skill, repos.user_skills, repos.knowledge,
        repos.bundles, repos.pack, repos.planner,
    )


class TestRequestDraft:
    async def test_rejects_when_quota_reached(self, service, repos):
        repos.skill.count_owned_active.return_value = 5

        with pytest.raises(ConflictError, match="at most 5 active private skills"):
            await service.request_draft(ACTOR, make_req())

        repos.job.create.assert_not_awaited()

    async def test_explicit_packs_with_queries_skip_planner_and_enqueue(self, service, repos, collect):
        packs = [pack(1), pack(2)]
        repos.pack.get_active_many.return_value = packs
        req = make_req(
            knowledge_pack_ids=[1, 1, 2], search_queries=[" joins ", " "],
            skill_name="sql", description="d", source_text="src",
        )

        job_id, status = await service.request_draft(ACTOR, req)

        assert (job_id, status) == (10, "pending")
        repos.pack.get_active_many.assert_awaited_once_with([1, 2])
        repos.planner.plan.assert_not_awaited()
        collect.assert_awaited_once_with(repos.knowledge, ["learn sql", "joins"], packs)
        payload = {
            "intent": "learn sql", "skill_name": "sql", "description": "d", "source_text": "src",
            "snippets": [{"text": "snippet"}], "retrieval_warnings": ["warn"],
        }
        repos.job.create.assert_awaited_once_with(
            job_type=JobType.SKILL_GENERATION, user_id=1, payload=payload
        )
        repos.arq.enqueue_job.assert_awaited_once_with(
            "run_skill_draft", 10, **payload,
            _job_id="skill_draft:10", _queue_name=INGESTION_QUEUE,
        )

    async def test_missing_explicit_pack_raises(self, service, repos):
        repos.pack.get_active_many.return_value = [pack(1)]

        with pytest.raises(NotFoundError, match=PACKS_UNAVAILABLE):
            await service.request_draft(ACTOR, make_req(knowledge_pack_ids=[1, 2]))

        repos.job.create.assert_not_awaited()

    async def test_packs_without_queries_ask_planner_for_queries_only(self, service, repos, collect):
        repos.pack.get_active_many.return_value = [pack(1)]
        repos.planner.plan.return_value = SimpleNamespace(pack_ids=[], queries=["q1", "learn sql"])

        await service.request_draft(ACTOR, make_req(knowledge_pack_ids=[1]))

        repos.planner.plan.assert_awaited_once_with("learn sql", pick_packs=False)
        assert collect.await_args.args[1] == ["learn sql", "q1"]

    async def test_auto_packs_lets_planner_pick_packs(self, service, repos, collect):
        picked = [pack(7)]
        repos.pack.get_active_many.return_value = picked
        repos.planner.plan.return_value = SimpleNamespace(pack_ids=[7], queries=["extra"])

        await service.request_draft(ACTOR, make_req(auto_packs=True))

        repos.planner.plan.assert_awaited_once_with("learn sql", pick_packs=True)
        repos.pack.get_active_many.assert_awaited_once_with([7])
        collect.assert_awaited_once_with(repos.knowledge, ["learn sql", "extra"], picked)

    async def test_auto_packs_ignored_when_packs_given(self, service, repos, collect):
        repos.pack.get_active_many.return_value = [pack(1)]

        await service.request_draft(
            ACTOR, make_req(auto_packs=True, knowledge_pack_ids=[1], search_queries=["q"])
        )

        repos.planner.plan.assert_not_awaited()

    async def test_no_packs_yields_warning_and_skips_retrieval(self, service, repos, collect):
        await service.request_draft(ACTOR, make_req())

        collect.assert_not_awaited()
        payload = repos.job.create.await_args.kwargs["payload"]
        assert payload["snippets"] == []
        assert payload["retrieval_warnings"] == [mod.WARN_NO_PACKS]

    async def test_auto_packs_without_planner_result_yields_warning(self, service, repos, collect):
        await service.request_draft(ACTOR, make_req(auto_packs=True))

        collect.assert_not_awaited()
        assert repos.job.create.await_args.kwargs["payload"]["retrieval_warnings"] == [mod.WARN_NO_PACKS]

    async def test_bundle_packs_are_checked_for_ownership_for_regular_user(self, service, repos, collect):
        repos.pack.list_for_bundle.return_value = [pack(1), pack(2, archived_at="x")]

        await service.request_draft(ACTOR, make_req(config_bundle_id=5, search_queries=["q"]))

        repos.bundles.get_bundle.assert_awaited_once_with(5, 1)
        used_packs = collect.await_args.args[2]
        assert [p.id for p in used_packs] == [1]

    async def test_admin_skips_ownership_check(self, service, repos, collect):
        repos.pack.list_for_bundle.return_value = [pack(1)]

        await service.request_draft(ADMIN, make_req(config_bundle_id=5, search_queries=["q"]))

        repos.bundles.get_bundle.assert_not_awaited()

    async def test_foreign_bundle_is_rejected(self, service, repos):
        repos.bundles.get_bundle.side_effect = NotFoundError("Config bundle not found")

        with pytest.raises(NotFoundError):
            await service.request_draft(ACTOR, make_req(config_bundle_id=5))

        repos.job.create.assert_not_awaited()

    async def test_explicit_pack_takes_precedence_over_bundle_duplicate(self, service, repos, collect):
        explicit = pack(1, slug="explicit")
        repos.pack.get_active_many.return_value = [explicit]
        repos.pack.list_for_bundle.return_value = [pack(1, slug="from-bundle"), pack(2)]

        await service.request_draft(
            ACTOR, make_req(knowledge_pack_ids=[1], config_bundle_id=5, search_queries=["q"])
        )

        used = collect.await_args.args[2]
        assert [p.id for p in used] == [1, 2]
        assert used[0].slug == "explicit"

    async def test_enqueue_failure_marks_job_failed(self, service, repos):
        repos.arq.enqueue_job.side_effect = RuntimeError("redis down")

        with pytest.raises(DraftQueueError, match="Queue unavailable"):
            await service.request_draft(ACTOR, make_req())

        repos.job.mark_failed.assert_awaited_once_with(10, "Enqueue failed: redis down")

    async def test_duplicate_job_id_marks_job_failed(self, service, repos):
        repos.arq.enqueue_job.return_value = None

        with pytest.raises(ConflictError, match="already enqueued"):
            await service.request_draft(ACTOR, make_req())

        repos.job.mark_failed.assert_awaited_once_with(10, "Duplicate arq job id")


class TestGetStatus:
    @pytest.mark.parametrize(
        "job",
        [None, make_job(user_id=999), make_job(job_type="other")],
        ids=["missing", "foreign", "wrong-type"],
    )
    async def test_hides_jobs_not_owned_or_of_other_type(self, service, repos, job):
        repos.job.get.return_value = job

        with pytest.raises(NotFoundError, match="Draft not found"):
            await service.get_status(ACTOR, 10)

    async def test_pending_job_has_no_draft(self, service, repos):
        repos.job.get.return_value = make_job(status="pending")

        status = await service.get_status(ACTOR, 10)

        assert status.job_id == 10
        assert status.status == "pending"
        assert status.draft is None
        assert status.error is None

    async def test_done_job_returns_draft_without_internal_key(self, service, repos):
        repos.job.get.return_value = make_job(
            result={"skill_name": "s", "content": "c", CONFIRMED_KEY: 3}
        )

        status = await service.get_status(ACTOR, 10)

        assert status.draft.skill_name == "s"
        assert not hasattr(status.draft, CONFIRMED_KEY)

    async def test_failed_job_hides_internal_error(self, service, repos):
        repos.job.get.return_value = make_job(status="failed", error="Traceback: secret")

        status = await service.get_status(ACTOR, 10)

        assert status.error == GENERIC_DRAFT_ERROR
        assert status.draft is None


class TestAttachUsedPacks:
    async def test_adds_pack_ids_to_bundle(self, service, repos):
        repos.job.get.return_value = make_job(
            result={"used_packs": [SimpleNamespace(id=1), SimpleNamespace(id=None), SimpleNamespace(id=3)]}
        )
        bundle = SimpleNamespace(id=7)
        repos.bundles.add_to_bundle.return_value = bundle

        assert await service.attach_used_packs(ACTOR, 10, 7) is bundle
        repos.bundles.add_to_bundle.assert_awaited_once_with(7, 1, knowledge_pack_ids=[1, 3])

    @pytest.mark.parametrize("job", [make_job(status="pending"), make_job(result=None)])
    async def test_requires_ready_draft(self, service, repos, job):
        repos.job.get.return_value = job

        with pytest.raises(ConflictError, match="Draft is not ready"):
            await service.attach_used_packs(ACTOR, 10, 7)

        repos.bundles.add_to_bundle.assert_not_awaited()


class TestConfirm:
    @pytest.fixture
    def draft_result(self):
        return {
            "skill_name": "draft-name", "description": "draft-desc", "content": "draft-body",
            "used_packs": [SimpleNamespace(id=1, domain_id=5), SimpleNamespace(id=2, domain_id=3),
                           SimpleNamespace(id=3, domain_id=5), SimpleNamespace(id=4, domain_id=None)],
        }

    @pytest.mark.parametrize("job", [make_job(status="pending"), make_job(result=None)])
    async def test_requires_ready_draft(self, service, repos, job):
        repos.job.get.return_value = job

        with pytest.raises(ConflictError, match="Draft is not ready"):
            await service.confirm(ACTOR, 10, SimpleNamespace())

        repos.user_skills.create_skill.assert_not_awaited()

    async def test_creates_skill_from_draft_with_domains_from_used_packs(self, service, repos, draft_result):
        repos.job.get.return_value = make_job(result=draft_result)
        skill = SimpleNamespace(id=42)
        repos.user_skills.create_skill.return_value = skill
        body = SimpleNamespace(skill_name=None, description=None, content=None, domain_ids=None)

        assert await service.confirm(ACTOR, 10, body) is skill

        repos.user_skills.create_skill.assert_awaited_once_with(
            ACTOR, "draft-name", "draft-desc", "draft-body", [3, 5]
        )
        repos.job.set_result.assert_awaited_once_with(10, {**draft_result, CONFIRMED_KEY: 42})

    async def test_user_edits_override_draft(self, service, repos, draft_result):
        repos.job.get.return_value = make_job(result=draft_result)
        repos.user_skills.create_skill.return_value = SimpleNamespace(id=1)
        body = SimpleNamespace(skill_name="mine", description="md", content="mc", domain_ids=[9])

        await service.confirm(ACTOR, 10, body)

        repos.user_skills.create_skill.assert_awaited_once_with(ACTOR, "mine", "md", "mc", [9])

    async def test_confirm_is_idempotent(self, service, repos, draft_result):
        repos.job.get.return_value = make_job(result={**draft_result, CONFIRMED_KEY: 42})
        existing = SimpleNamespace(id=42)
        repos.user_skills.get_skill.return_value = existing

        assert await service.confirm(ACTOR, 10, SimpleNamespace()) is existing

        repos.user_skills.get_skill.assert_awaited_once_with(ACTOR, 42)
        repos.user_skills.create_skill.assert_not_awaited()

    async def test_recreates_skill_when_confirmed_one_was_deleted(self, service, repos, draft_result):
        repos.job.get.return_value = make_job(result={**draft_result, CONFIRMED_KEY: 42})
        repos.user_skills.get_skill.side_effect = NotFoundError("Skill not found")
        repos.user_skills.create_skill.return_value = SimpleNamespace(id=43)
        body = SimpleNamespace(skill_name=None, description=None, content=None, domain_ids=None)

        result = await service.confirm(ACTOR, 10, body)

        assert result.id == 43
        repos.job.set_result.assert_awaited_once()
        assert repos.job.set_result.await_args.args[1][CONFIRMED_KEY] == 43

    async def test_foreign_job_is_hidden(self, service, repos):
        repos.job.get.return_value = make_job(user_id=999)

        with pytest.raises(NotFoundError):
            await service.confirm(ACTOR, 10, SimpleNamespace())


class TestSuggestPacks:
    async def test_returns_packs_in_planner_order(self, service, repos):
        repos.planner.plan.return_value = SimpleNamespace(pack_ids=[3, 1], queries=["q"])
        repos.pack.get_active_many.return_value = [pack(1), pack(3)]

        result = await service.suggest_packs("intent")

        repos.planner.plan.assert_awaited_once_with("intent", pick_packs=True)
        repos.pack.get_active_many.assert_awaited_once_with([3, 1])
        assert [p.id for p in result.packs] == [3, 1]
        assert result.queries == ["q"]

    async def test_archived_or_unknown_packs_are_dropped(self, service, repos):
        repos.planner.plan.return_value = SimpleNamespace(pack_ids=[1, 2], queries=[])
        repos.pack.get_active_many.return_value = [pack(2)]

        result = await service.suggest_packs("intent")

        assert [p.id for p in result.packs] == [2]


class TestSplitResult:
    def test_extracts_confirmed_id_without_mutating_input(self):
        original = {"a": 1, CONFIRMED_KEY: 5}

        data, confirmed = SkillDraftService._split_result(original)

        assert data == {"a": 1}
        assert confirmed == 5
        assert original == {"a": 1, CONFIRMED_KEY: 5}

    def test_missing_key(self):
        assert SkillDraftService._split_result({"a": 1}) == ({"a": 1}, None)