import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from src.db.db_connection import Base
from src.db.models.users import User
from src.db.models.agent_profiles import AgentProfile
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition
from src.db.models.config_bundles import ConfigBundle
from src.db.models.token_usage_events import TokenUsageEvent
from src.db.models.device_code import DeviceCode
from src.db.enums.device_code_status import DeviceStatus
from src.test_config import test_settings


TEST_DATABASE = test_settings.TEST_DATABASE_URL


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(TEST_DATABASE, echo=False, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    async_session_maker = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with async_session_maker() as session:
        proxy = SessionFactoryProxy(session)
        yield proxy
        await session.rollback()


class SessionFactoryProxy:

    def __init__(self, session: AsyncSession):
        self._session = session

    def __call__(self):
        return self._session_cm()

    @asynccontextmanager
    async def _session_cm(self):
        yield self._session

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest_asyncio.fixture
async def sample_user(db_session):
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def another_user(db_session):
    user = User(
        username="anotheruser",
        email="another@example.com",
        password_hash="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_agent_profile(db_session):
    agent = AgentProfile(
        agent_name="test-agent",
        description="Testing agent-profile",
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


@pytest_asyncio.fixture
async def another_agent_profile(db_session):
    agent = AgentProfile(
        agent_name="another-agent",
        description="Another test agent",
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


@pytest_asyncio.fixture
async def sample_skill(db_session):
    skill = Skill(
        skill_name="summarization",
        description="Summarize text",
    )
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)
    return skill


@pytest_asyncio.fixture
async def another_skill(db_session):
    skill = Skill(
        skill_name="translation",
        description="Translate text skill",
    )
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)
    return skill

@pytest_asyncio.fixture
async def sample_tool(db_session):
    tool = ToolDefinition(
        tool_name="web_search",
        description="Searching info in internet",
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest_asyncio.fixture
async def another_tool(db_session):
    tool = ToolDefinition(
        tool_name="code_execution",
        description="Test code in sandbox",
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest_asyncio.fixture
async def agent_profile_with_skill_and_tool(
    db_session, sample_agent_profile, sample_skill, sample_tool
):
    sample_agent_profile.skills.append(sample_skill)
    sample_agent_profile.tools.append(sample_tool)
    db_session.add(sample_agent_profile)
    await db_session.commit()
    await db_session.refresh(sample_agent_profile)
    return sample_agent_profile


@pytest_asyncio.fixture
async def sample_config_bundle(db_session, sample_user, sample_agent_profile):
    bundle = ConfigBundle(
        user_id=sample_user.id,
        agent_id=sample_agent_profile.id,
        name="default-bundle",
        description="Test conf-bundle",
    )
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)
    return bundle


@pytest_asyncio.fixture
async def config_bundle_with_skill_and_tool(
    db_session, sample_config_bundle, sample_skill, sample_tool
):
    sample_config_bundle.skills.append(sample_skill)
    sample_config_bundle.tools.append(sample_tool)
    db_session.add(sample_config_bundle)
    await db_session.commit()
    await db_session.refresh(sample_config_bundle)
    return sample_config_bundle


@pytest_asyncio.fixture
async def sample_token_usage_event(db_session, sample_user, sample_agent_profile):
    event = TokenUsageEvent(
        user_id=sample_user.id,
        agent_id=sample_agent_profile.id,
        tokens_used=1500,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event

@pytest_asyncio.fixture
async def sample_device_code(db_session, sample_user):
    device_code = DeviceCode(
        device_code="ABCD-1234",
        user_id=sample_user.id,
        status=DeviceStatus.PENDING,
        scope="read write",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        interval=5,
    )
    db_session.add(device_code)
    await db_session.commit()
    await db_session.refresh(device_code)
    return device_code


@pytest_asyncio.fixture
async def approved_device_code(db_session, sample_user):
    device_code = DeviceCode(
        device_code="EFGH-5678",
        user_id=sample_user.id,
        status=DeviceStatus.APPROVED,
        scope="read write",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        interval=5,
    )
    db_session.add(device_code)
    await db_session.commit()
    await db_session.refresh(device_code)
    return device_code