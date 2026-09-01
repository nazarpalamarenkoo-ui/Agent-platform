import asyncio
import sys
import pytest

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


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
from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.tags import Tag
from src.db.models.document import Document
from src.db.models.document_chunks import DocumentChunk
from src.db.models.skill_usage_events import SkillUsageEvent
from src.db.models.tool_usage_events import ToolUsageEvent

from src.db.models.agent_profile_skills import AgentProfileSkill
from src.db.models.agent_profile_tools import AgentProfileTool
from src.db.models.config_bundle_skills import ConfigBundleSkill
from src.db.models.config_bunlde_tools import ConfigBundleTool
from src.db.models.document_tags import DocumentTag
from src.db.models.skills_domain import SkillDomain

from src.db.enums.device_code_status import DeviceStatus
from src.db.enums.document_status import DocumentStatus
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.test_config import test_settings


TEST_DATABASE = test_settings.TEST_DATABASE_URL


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DATABASE, echo=False, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    async with db_engine.connect() as conn:
        trans = await conn.begin()
        async_session_maker = async_sessionmaker(
            bind=conn, class_=AsyncSession, expire_on_commit=False,
            join_transaction_mode="create_savepoint"
        )
        async with async_session_maker() as session:
            proxy = SessionFactoryProxy(session)
            yield proxy
        await trans.rollback()


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
async def sample_knowledge_domain(db_session):
    domain = KnowledgeDomain(
        slug="backend-api-design",
        name="Backend API Design",
        description="Designing backend APIs regardless of framework",
    )
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)
    return domain


@pytest_asyncio.fixture
async def another_knowledge_domain(db_session):
    domain = KnowledgeDomain(
        slug="driver-development",
        name="Driver Development",
        description="Designing low-level drivers across languages",
    )
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)
    return domain


@pytest_asyncio.fixture
async def child_knowledge_domain(db_session, sample_knowledge_domain):
    domain = KnowledgeDomain(
        slug="rest-api-design",
        name="REST API Design",
        description="REST-specific conventions, nested under backend-api-design",
        parent_domain_id=sample_knowledge_domain.id,
    )
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)
    return domain


@pytest_asyncio.fixture
async def sample_skill(db_session, sample_knowledge_domain):
    skill = Skill(
        skill_name="summarization",
        description="Summarize text",
        domain_id=sample_knowledge_domain.id,
    )
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)
    return skill


@pytest_asyncio.fixture
async def another_skill(db_session, sample_knowledge_domain):
    skill = Skill(
        skill_name="translation",
        description="Translate text skill",
        domain_id=sample_knowledge_domain.id,
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
async def domain_scoped_tool(db_session, another_knowledge_domain):
    tool = ToolDefinition(
        tool_name="c_driver_docs_tool",
        description="Live docs lookup scoped to driver development",
        domain_id=another_knowledge_domain.id,
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


@pytest_asyncio.fixture
async def sample_tag(db_session):
    tag = Tag(tag_name="system-design")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    return tag


@pytest_asyncio.fixture
async def another_tag(db_session):
    tag = Tag(tag_name="driver-architecture")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    return tag


@pytest_asyncio.fixture
async def sample_document(db_session):
    document = Document(
        source="https://example.com/designing-data-intensive-applications.pdf",
        document_type=DocumentType.BOOK,
        size=204_800,
        content_hash="a" * 64,
        version=1,
        scraped_at=datetime.now(timezone.utc),
        status=DocumentStatus.PENDING,
        embedding_model="text-embedding-3-large",
        knowledge_type=KnowledgeType.REFERENCE,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document


@pytest_asyncio.fixture
async def classified_document(db_session, sample_knowledge_domain):
    document = Document(
        source="https://example.com/backend-api-design-patterns.pdf",
        domain_id=sample_knowledge_domain.id,
        document_type=DocumentType.ARCHITECTURE_DOC,
        size=102_400,
        content_hash="b" * 64,
        version=1,
        scraped_at=datetime.now(timezone.utc),
        status=DocumentStatus.INDEXED,
        embedding_model="text-embedding-3-large",
        knowledge_type=KnowledgeType.PRINCIPLE,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document


@pytest_asyncio.fixture
async def sample_document_chunk(db_session, classified_document):
    chunk = DocumentChunk(
        document_id=classified_document.id,
        chunk_index=0,
        qdrant_point_id="point-0001",
        token_count=512,
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(chunk)
    return chunk


@pytest_asyncio.fixture
async def sample_skill_usage_event(db_session, sample_skill, sample_user, sample_config_bundle):
    event = SkillUsageEvent(
        skill_id=sample_skill.id,
        user_id=sample_user.id,
        config_bundle_id=sample_config_bundle.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


@pytest_asyncio.fixture
async def sample_tool_usage_event(db_session, sample_tool, sample_user, sample_config_bundle):
    event = ToolUsageEvent(
        tool_id=sample_tool.id,
        user_id=sample_user.id,
        config_bundle_id=sample_config_bundle.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event