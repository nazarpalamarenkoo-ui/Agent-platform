import asyncio
import dataclasses
import json
import logging
from typing import Any, Awaitable, Callable

from src.repositories.background_job_repo import BackgroundJobRepository

logger = logging.getLogger(__name__)


def to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):  # pydantic v2
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        obj = dataclasses.asdict(obj)
    return json.loads(json.dumps(obj, default=str))


async def run_tracked_job(
    job_repo: BackgroundJobRepository,
    job_id: int,
    work: Callable[[], Awaitable[Any]],
) -> dict:
    await job_repo.mark_running(job_id)
    try:
        result = to_jsonable(await work())
    except asyncio.CancelledError:
        await asyncio.shield(
            job_repo.mark_failed(job_id, "Cancelled (job timeout or worker shutdown)")
        )
        raise
    except Exception as exc:
        logger.exception("Background job %d failed", job_id)
        await job_repo.mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        return {"job_id": job_id, "status": "failed"}

    await job_repo.mark_done(job_id, result)
    return {"job_id": job_id, "status": "done"}