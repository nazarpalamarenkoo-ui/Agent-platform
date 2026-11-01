import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI

from src.api.auth.admin.routes import router as admin_auth_router
from src.api.auth.routes import router as auth_router
from src.api.routers.admin import router as admin_router
from src.api.routers.agents import router as agents_router
from src.api.routers.catalog import router as catalog_router
from src.api.routers.config_bundles import router as config_bundles_router
from src.api.routers.device import router as device_router
from src.api.routers.domains import router as domain_router
from src.api.routers.knowledge import router as knowledge_router
from src.api.routers.knowledge_pack import router as knowledge_pack_router
from src.api.routers.notifications import router as notifications_router
from src.api.routers.skills import router as skills_router
from src.api.routers.tools import router as tools_router
from src.api.routers.users import router as users_router
from src.api.routers.user_skills import router as user_skills_router
from src.api.routers.my_tools import router as my_tools_router
from src.api.routers.user_content import router as user_content_router
from src.config import settings
from src.db.db_connection import dispose_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    try:
        yield
    finally:
        try:
            close = getattr(app.state.arq_pool, "aclose", None) or app.state.arq_pool.close
            await close()
        except Exception:
            logger.exception("Failed to close arq pool")
        await dispose_engine()


app = FastAPI(
    title="Knowledge API",
    lifespan=lifespan,
)

for router in (
    knowledge_router,
    users_router,
    agents_router,
    config_bundles_router,
    tools_router,
    skills_router,
    device_router,
    domain_router,
    knowledge_pack_router,
    auth_router,
    admin_auth_router,
    admin_router,
    notifications_router,
    catalog_router,
    user_skills_router,
    my_tools_router,
    user_content_router,
):
    app.include_router(router)