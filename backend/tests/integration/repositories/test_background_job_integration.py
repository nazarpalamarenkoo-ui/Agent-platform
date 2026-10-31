import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.models.background_jobs import BackgroundJob, JobStatus, JobType
from src.repositories.background_job_repo import MAX_ERROR_LEN, BackgroundJobRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def job_repo(db_session):
    return BackgroundJobRepository(session_factory=db_session)


async def fresh(session, job_id) -> BackgroundJob | None:
    result = await session.execute(
        select(BackgroundJob)
        .where(BackgroundJob.id == job_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def new_job(job_repo, **overrides) -> BackgroundJob:
    data = dict(job_type=JobType.DISCOVERY_INGEST, user_id=None, payload={"q": "x"})
    data.update(overrides)
    return await job_repo.create(**data)


class TestCreate:

    async def test_creates_pending_job_with_payload(self, job_repo, db_session, sample_user):
        job = await job_repo.create(
            job_type=JobType.SKILL_GENERATION,
            user_id=sample_user.id,
            payload={"skill": "abc", "n": 3},
        )

        reloaded = await fresh(db_session, job.id)
        assert reloaded.id is not None
        assert reloaded.status == JobStatus.PENDING.value
        assert reloaded.job_type == JobType.SKILL_GENERATION.value
        assert reloaded.user_id == sample_user.id
        assert reloaded.payload == {"skill": "abc", "n": 3}
        assert reloaded.result is None
        assert reloaded.error is None
        assert reloaded.started_at is None
        assert reloaded.finished_at is None

    async def test_accepts_plain_string_job_type(self, job_repo, db_session):
        job = await new_job(job_repo, job_type="discovery_ingest")

        assert (await fresh(db_session, job.id)).job_type == "discovery_ingest"

    async def test_user_is_optional(self, job_repo, db_session):
        job = await new_job(job_repo, user_id=None)

        assert (await fresh(db_session, job.id)).user_id is None

    async def test_unknown_user_violates_foreign_key(self, job_repo, db_session):
        with pytest.raises(IntegrityError):
            await new_job(job_repo, user_id=999_999)

        await db_session.rollback()


class TestGet:

    async def test_returns_created_job(self, job_repo):
        job = await new_job(job_repo)

        assert (await job_repo.get(job.id)).id == job.id

    async def test_returns_none_for_unknown_id(self, job_repo):
        assert await job_repo.get(999_999) is None


class TestStatusTransitions:

    async def test_mark_running_sets_status_and_started_at(self, job_repo, db_session):
        job = await new_job(job_repo)

        await job_repo.mark_running(job.id)

        reloaded = await fresh(db_session, job.id)
        assert reloaded.status == JobStatus.RUNNING.value
        assert reloaded.started_at is not None
        assert reloaded.started_at.tzinfo is not None
        assert reloaded.finished_at is None

    async def test_mark_done_sets_status_result_and_finished_at(self, job_repo, db_session):
        job = await new_job(job_repo)
        await job_repo.mark_running(job.id)

        await job_repo.mark_done(job.id, {"saved": 7})

        reloaded = await fresh(db_session, job.id)
        assert reloaded.status == JobStatus.DONE.value
        assert reloaded.result == {"saved": 7}
        assert reloaded.finished_at is not None
        assert reloaded.started_at is not None

    async def test_mark_done_accepts_empty_result(self, job_repo, db_session):
        job = await new_job(job_repo)

        await job_repo.mark_done(job.id, None)

        reloaded = await fresh(db_session, job.id)
        assert reloaded.status == JobStatus.DONE.value
        assert reloaded.result is None

    async def test_mark_failed_sets_status_error_and_finished_at(self, job_repo, db_session):
        job = await new_job(job_repo)

        await job_repo.mark_failed(job.id, "boom")

        reloaded = await fresh(db_session, job.id)
        assert reloaded.status == JobStatus.FAILED.value
        assert reloaded.error == "boom"
        assert reloaded.finished_at is not None

    async def test_mark_failed_truncates_long_errors(self, job_repo, db_session):
        job = await new_job(job_repo)

        await job_repo.mark_failed(job.id, "e" * (MAX_ERROR_LEN + 500))

        reloaded = await fresh(db_session, job.id)
        assert len(reloaded.error) == MAX_ERROR_LEN

    async def test_set_result_does_not_change_status(self, job_repo, db_session):
        job = await new_job(job_repo)
        await job_repo.mark_running(job.id)

        await job_repo.set_result(job.id, {"progress": 50})

        reloaded = await fresh(db_session, job.id)
        assert reloaded.status == JobStatus.RUNNING.value
        assert reloaded.result == {"progress": 50}
        assert reloaded.finished_at is None

    async def test_updates_only_the_targeted_job(self, job_repo, db_session):
        target = await new_job(job_repo)
        bystander = await new_job(job_repo)

        await job_repo.mark_running(target.id)

        assert (await fresh(db_session, bystander.id)).status == JobStatus.PENDING.value

    async def test_updating_unknown_job_is_a_noop(self, job_repo, db_session):
        await job_repo.mark_running(999_999)
        await job_repo.mark_failed(999_999, "nobody home")

        assert await fresh(db_session, 999_999) is None


class TestFailStaleRunning:

    async def test_fails_only_running_jobs_and_returns_count(self, job_repo, db_session):
        pending = await new_job(job_repo)
        running_a = await new_job(job_repo)
        running_b = await new_job(job_repo)
        done = await new_job(job_repo)
        failed = await new_job(job_repo)
        await job_repo.mark_running(running_a.id)
        await job_repo.mark_running(running_b.id)
        await job_repo.mark_done(done.id, {"ok": True})
        await job_repo.mark_failed(failed.id, "earlier failure")

        affected = await job_repo.fail_stale_running("server restarted")

        assert affected == 2
        for job in (running_a, running_b):
            reloaded = await fresh(db_session, job.id)
            assert reloaded.status == JobStatus.FAILED.value
            assert reloaded.error == "server restarted"
            assert reloaded.finished_at is not None
        assert (await fresh(db_session, pending.id)).status == JobStatus.PENDING.value
        assert (await fresh(db_session, done.id)).status == JobStatus.DONE.value
        assert (await fresh(db_session, failed.id)).error == "earlier failure"

    async def test_returns_zero_when_nothing_is_running(self, job_repo):
        await new_job(job_repo)

        assert await job_repo.fail_stale_running("restart") == 0

    async def test_truncates_reason(self, job_repo, db_session):
        job = await new_job(job_repo)
        await job_repo.mark_running(job.id)

        await job_repo.fail_stale_running("r" * (MAX_ERROR_LEN + 10))

        assert len((await fresh(db_session, job.id)).error) == MAX_ERROR_LEN