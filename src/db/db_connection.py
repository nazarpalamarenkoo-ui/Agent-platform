from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool
from src.config import settings
from contextlib import asynccontextmanager

DATABASE_URL = settings.DATABASE_URL_LOCAL

Base = declarative_base()

POOL_SIZE = getattr(settings.DB_POOL_SIZE, "DB_POOL_SIZE", 10)
MAX_OVERFLOW = getattr(settings.DB_MAX_OVERFLOW, "DB_MAX_OVERFLOW", 20)
POOL_TIMEOUT = getattr(settings.DB_POOL_TIMEOUT, "DB_POOL_TIMEOUT", 30)          
POOL_RECYCLE = getattr(settings.DB_POOL_RECYCLE, "DB_POOL_RECYCLE", 1800)        
POOL_PRE_PING = getattr(settings.DB_POOL_PRE_PING, "DB_POOL_PRE_PING", True)      
USE_NULLPOOL = getattr(settings.DB_USE_NULLPOOL, "DB_USE_NULLPOOL", False)       

if USE_NULLPOOL:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        future=True,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        future=True,
        poolclass=AsyncAdaptedQueuePool,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_recycle=POOL_RECYCLE,
        pool_pre_ping=POOL_PRE_PING,
    )


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def get_db_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def dispose_engine():
    await engine.dispose()