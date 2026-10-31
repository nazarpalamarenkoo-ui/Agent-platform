import inspect
import logging

import httpx
from arq.connections import RedisSettings
from qdrant_client import AsyncQdrantClient

from src.config import settings
from src.db.db_connection import dispose_engine
from src.dependencies import BROWSER_HEADERS
from src.knowledge.acquisition.judge.judge_llm_client import JudgeLLMClient
from src.rag.embeddings.bge_m3 import Embedding
from src.repositories.background_job_repo import BackgroundJobRepository
from src.worker.deps import (
    build_corpus_builder,
    build_draft_generator,
    build_llm_client,
)
from src.worker.queues import INGESTION_QUEUE
from src.worker.tasks.discovery import run_discovery_ingest
from src.worker.tasks.skill_draft import run_skill_draft

logger = logging.getLogger("arq.worker")

REQUIRED_CTX_KEYS = (
    "job_repo",
    "qdrant",
    "embedding",
    "http",
    "fetch_http",
    "judge_client",
    "corpus_builder",
    "llm_client",
    "draft_generator",
)


async def _close_if_possible(obj) -> None:
    closer = getattr(obj, "aclose", None) or getattr(obj, "close", None)
    if closer is None:
        return
    result = closer()
    if inspect.isawaitable(result):
        await result


async def startup(ctx: dict) -> None:
    logger.info("worker_startup_begin")

    ctx["job_repo"] = BackgroundJobRepository()

    stale = await ctx["job_repo"].fail_stale_running(
        "Worker restarted while job was running"
    )
    if stale:
        logger.warning("Marked %d stale running job(s) as failed", stale)

    ctx["qdrant"] = AsyncQdrantClient(url=settings.QDRANT_URL)
    ctx["embedding"] = Embedding()
    ctx["http"] = httpx.AsyncClient(follow_redirects=True)
    ctx["fetch_http"] = httpx.AsyncClient(
        follow_redirects=True, headers=BROWSER_HEADERS
    )
    ctx["judge_client"] = JudgeLLMClient(
        base_url=settings.JUDGE_BASE_URL,
        model=settings.JUDGE_MODEL,
        api_key=settings.JUDGE_API_KEY,
        timeout=settings.JUDGE_TIMEOUT,
        max_tokens=settings.JUDGE_MAX_TOKENS,
        use_json_schema=settings.JUDGE_USE_JSON_SCHEMA,
    )
    ctx["corpus_builder"] = await build_corpus_builder(
        qdrant=ctx["qdrant"],
        embedding=ctx["embedding"],
        http=ctx["http"],
        fetch_http=ctx["fetch_http"],
        judge_client=ctx["judge_client"],
    )
    ctx["llm_client"] = build_llm_client()
    ctx["draft_generator"] = build_draft_generator(llm_client=ctx["llm_client"])

    missing = [key for key in REQUIRED_CTX_KEYS if ctx.get(key) is None]
    if missing:
        raise RuntimeError(f"Worker ctx is missing required keys: {missing}")

    logger.info("worker_startup_done")


async def shutdown(ctx: dict) -> None:
    logger.info("worker_shutdown_begin")
    for key in ("http", "fetch_http"):
        client = ctx.get(key)
        if client is not None:
            await client.aclose()
    for key in ("judge_client", "llm_client"):
        client = ctx.get(key)
        if client is not None:
            await _close_if_possible(client)
    qdrant = ctx.get("qdrant")
    if qdrant is not None:
        await qdrant.close()
    await dispose_engine()
    logger.info("worker_shutdown_done")


class WorkerSettings:
    functions = [run_discovery_ingest, run_skill_draft]
    queue_name = INGESTION_QUEUE
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    max_jobs = 2
    job_timeout = 30 * 60
    max_tries = 1
    retry_jobs = False
    keep_result = 3600
    job_completion_wait = 120