import logging

from arq.connections import ArqRedis
from fastapi import Depends

from src.api.auth.auth import get_current_user
from src.api.routers.errors import too_many_requests
from src.config import settings
from src.db.models.users import User
from src.dependencies import get_arq_pool

logger = logging.getLogger(__name__)

HINT_WINDOW_SECONDS = 3600
HINT_DEFAULT_LIMIT = 20

DRAFT_WINDOW_SECONDS = 3600
DRAFT_DEFAULT_LIMIT = 5


async def check_rate_limit(redis, key: str, limit: int, window_seconds: int) -> None:
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(key, 0, ex=window_seconds, nx=True)
            pipe.incr(key)
            pipe.ttl(key)
            _, count, ttl = await pipe.execute()
    except Exception:
        logger.warning("Rate limiter unavailable, failing open for %s", key, exc_info=True)
        return

    if count > limit:
        raise too_many_requests(retry_after=max(int(ttl), 1))


async def enforce_hint_rate_limit(
    actor: User = Depends(get_current_user),
    redis: ArqRedis = Depends(get_arq_pool),
) -> None:
    limit = getattr(settings, "HINT_RATE_LIMIT_PER_HOUR", HINT_DEFAULT_LIMIT)
    await check_rate_limit(redis, f"ratelimit:hint:{actor.id}", limit, HINT_WINDOW_SECONDS)


async def enforce_draft_rate_limit(
    actor: User = Depends(get_current_user),
    redis: ArqRedis = Depends(get_arq_pool),
) -> None:
    limit = getattr(settings, "DRAFT_RATE_LIMIT_PER_HOUR", DRAFT_DEFAULT_LIMIT)
    await check_rate_limit(redis, f"ratelimit:draft:{actor.id}", limit, DRAFT_WINDOW_SECONDS)