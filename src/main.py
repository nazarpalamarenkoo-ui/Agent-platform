from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.db.db_connection import dispose_engine
from src.api.routers.knowledge import router as knowledge_router
from src.api.routers.users import router as users_router
from src.api.routers.agents import router as agents_router
from src.api.routers.config_bundles import router as config_bundles_router
from src.api.routers.tools import router as tools_router
from src.api.routers.skills import router as skills_router
from src.api.routers.device import router as device_router
from src.api.routers.domains import router as domain_router
from src.api.routers.knowledge_pack import router as knowledge_pack_router
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await dispose_engine()


app = FastAPI(
    title="Knowledge API",
    lifespan=lifespan,
)

app.include_router(knowledge_router)
app.include_router(users_router)
app.include_router(agents_router)
app.include_router(config_bundles_router)
app.include_router(tools_router)
app.include_router(skills_router)
app.include_router(device_router)
app.include_router(domain_router)
app.include_router(knowledge_pack_router)