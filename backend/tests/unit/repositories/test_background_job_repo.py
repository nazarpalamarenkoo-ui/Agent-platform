import pytest
from sqlalchemy import select

from src.db.models.background_jobs import BackgroundJob, JobStatus, JobType
from src.repositories.background_job_repo import (
    MAX_ERROR_LEN,
    BackgroundJobRepository,
)

pytestmark = pytest.mark.db


@pytest.fixture
def job_repo(db_session):
    return BackgroundJobRepository(db_session)


@pytest.fixture
def job_type():
    return list(JobType)[0]


@pytest.fixture
def reload(db_session):
    async def _reload(job_id: int) -> BackgroundJob:
        result = await db_session.execute(
            select(BackgroundJob)
            .where(BackgroundJob.id == job_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    return _reload


class TestCreateAndGet:

    async def test_create_starts_pending_with_payload(
        self, job_repo, job_type, make_user
    ):
        user = await make_user()

        job = await job_repo.create(
            job_type=job_type, user_id=user.id, payload={"url": "https://a.com"}
        )

        assert job.id is not None
        assert job.job_type == job_type.value
        assert job.status == JobStatus.PENDING.value
        assert job.user_id == user.id
        assert job.payload == {"url": "https://a.com"}
        assert job.started_at is None
        assert job.finished_at is None

    async def test_create_accepts_plain_string_job_type(self, job_repo, job_type):
        job = await job_repo.create(
            job_type=job_type.value, user_id=None, payload={}
        )

        assert job.job_type == job_type.value
        assert job.user_id is None

    async def test_get_returns_job_or_none(self, job_repo, job_type):
        job = await job_repo.create(job_type=job_type, user_id=None, payload={})

        assert (await job_repo.get(job.id)).id == job.id
        assert await job_repo.get(999999) is None


class TestStatusTransitions:

    async def test_mark_running_sets_status_and_started_at(
        self, job_repo, job_type, reload
    ):
        job = await job_repo.create(job_type=job_type, user_id=None, payload={})

        await job_repo.mark_running(job.id)

        job = await reload(job.id)
        assert job.status == JobStatus.RUNNING.value
        assert job.started_at is not None
        assert job.finished_at is None

    async def test_mark_done_stores_result_and_finished_at(
        self, job_repo, job_type, reload
    ):
        job = await job_repo.create(job_type=job_type, user_id=None, payload={})

        await job_repo.mark_done(job.id, {"saved": 3})

        job = await reload(job.id)
        assert job.status == JobStatus.DONE.value
        assert job.result == {"saved": 3}
        assert job.finished_at is not None

    async def test_mark_done_accepts_none_result(self, job_repo, job_type, reload):
        job = await job_repo.create(job_type=job_type, user_id=None, payload={})

        await job_repo.mark_done(job.id, None)

        job = await reload(job.id)
        assert job.status == JobStatus.DONE.value
        assert job.result is None

    async def test_set_result_does_not_change_status(self, job_repo, job_type, reload):
        job = await job_repo.create(job_type=job_type, user_id=None, payload={})
        await job_repo.mark_running(job.id)

        await job_repo.set_result(job.id, {"progress": 50})

        job = await reload(job.id)
        assert job.status == JobStatus.RUNNING.value
        assert job.result == {"progress": 50}
        assert job.finished_at is None

    async def test_mark_failed_stores_error_and_finished_at(
        self, job_repo, job_type, reload
    ):
        job = await job_repo.create(job_type=job_type, user_id=None, payload={})

        await job_repo.mark_failed(job.id, "boom")

        job = await reload(job.id)
        assert job.status == JobStatus.FAILED.value
        assert job.error == "boom"
        assert job.finished_at is not None

    async def test_mark_failed_truncates_long_error(self, job_repo, job_type, reload):
        job = await job_repo.create(job_type=job_type, user_id=None, payload={})

        await job_repo.mark_failed(job.id, "x" * (MAX_ERROR_LEN + 500))

        job = await reload(job.id)
        assert len(job.error) == MAX_ERROR_LEN

    async def test_update_of_unknown_job_is_a_noop(self, job_repo):
        await job_repo.mark_running(999999)
        await job_repo.mark_failed(999999, "nope")

        assert await job_repo.get(999999) is None


class TestFailStaleRunning:

    async def test_fails_only_running_jobs(self, job_repo, job_type, reload):
        pending = await job_repo.create(job_type=job_type, user_id=None, payload={})
        running_a = await job_repo.create(job_type=job_type, user_id=None, payload={})
        running_b = await job_repo.create(job_type=job_type, user_id=None, payload={})
        done = await job_repo.create(job_type=job_type, user_id=None, payload={})
        await job_repo.mark_running(running_a.id)
        await job_repo.mark_running(running_b.id)
        await job_repo.mark_done(done.id, {})

        count = await job_repo.fail_stale_running("server restarted")

        assert count == 2
        for job_id in (running_a.id, running_b.id):
            job = await reload(job_id)
            assert job.status == JobStatus.FAILED.value
            assert job.error == "server restarted"
            assert job.finished_at is not None
        assert (await reload(pending.id)).status == JobStatus.PENDING.value
        assert (await reload(done.id)).status == JobStatus.DONE.value

    async def test_returns_zero_when_nothing_is_running(self, job_repo, job_type):
        await job_repo.create(job_type=job_type, user_id=None, payload={})

        assert await job_repo.fail_stale_running("restart") == 0

    async def test_truncates_reason(self, job_repo, job_type, reload):
        job = await job_repo.create(job_type=job_type, user_id=None, payload={})
        await job_repo.mark_running(job.id)

        await job_repo.fail_stale_running("r" * (MAX_ERROR_LEN + 10))

        assert len((await reload(job.id)).error) == MAX_ERROR_LEN