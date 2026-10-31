from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy import update

from src.db.db_connection import get_db
from src.db.models.background_jobs import BackgroundJob, JobStatus, JobType

session_scope = asynccontextmanager(get_db)

MAX_ERROR_LEN = 2000


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BackgroundJobRepository:
    def __init__(self, session_factory=session_scope):
        self._session_factory = session_factory

    async def create(
        self, *, job_type: JobType | str, user_id: int | None, payload: dict
    ) -> BackgroundJob:
        async with self._session_factory() as session:
            job = BackgroundJob(
                job_type=getattr(job_type, "value", job_type),
                status=JobStatus.PENDING.value,
                user_id=user_id,
                payload=payload,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job

    async def get(self, job_id: int) -> BackgroundJob | None:
        async with self._session_factory() as session:
            return await session.get(BackgroundJob, job_id)

    async def mark_running(self, job_id: int) -> None:
        await self._update(
            job_id, status=JobStatus.RUNNING.value, started_at=_now()
        )

    async def mark_done(self, job_id: int, result: dict | None) -> None:
        await self._update(
            job_id,
            status=JobStatus.DONE.value,
            result=result,
            finished_at=_now(),
        )

    async def set_result(self, job_id: int, result: dict | None) -> None:
        await self._update(job_id, result=result)

    async def mark_failed(self, job_id: int, error: str) -> None:
        await self._update(
            job_id,
            status=JobStatus.FAILED.value,
            error=error[:MAX_ERROR_LEN],
            finished_at=_now(),
        )

    async def fail_stale_running(self, reason: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                update(BackgroundJob)
                .where(BackgroundJob.status == JobStatus.RUNNING.value)
                .values(
                    status=JobStatus.FAILED.value,
                    error=reason[:MAX_ERROR_LEN],
                    finished_at=_now(),
                )
            )
            await session.commit()
            return result.rowcount or 0

    async def _update(self, job_id: int, **values) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(BackgroundJob)
                .where(BackgroundJob.id == job_id)
                .values(**values)
            )
            await session.commit()