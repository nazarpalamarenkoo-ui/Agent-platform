import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from src.db.models.users import User
from src.db.models.agent_profiles import AgentProfile
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition
from src.db.models.config_bundles import ConfigBundle
from src.db.models.token_usage_events import TokenUsageEvent
from src.db.models.device_code import DeviceCode
from src.db.models.agent_profile_skills import AgentProfileSkill
from src.db.models.agent_profile_tools import AgentProfileTool
from src.db.models.config_bundle_skills import ConfigBundleSkill
from src.db.models.config_bunlde_tools import ConfigBundleTool
from src.db.enums.device_code_status import DeviceStatus


pytestmark = pytest.mark.unit

async def test_user_creation(db_session):
    user = User(username="john", email="john@example.com", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.username == "john"
    assert user.email == "john@example.com"
    assert user.password_hash == "hashed"
    assert user.created_at is not None
    assert user.token_limit == 100_000
    assert user.tokens_used == 0


async def test_user_username_must_be_unique(db_session, sample_user):
    duplicate = User(username=sample_user.username, email="different@example.com", password_hash="hashed")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_user_email_must_be_unique(db_session, sample_user):
    duplicate = User(username="different_username", email=sample_user.email, password_hash="hashed")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_user_repr(sample_user):
    assert repr(sample_user) == f"<User id={sample_user.id} username={sample_user.username}>"


async def test_skill_creation(db_session):
    skill = Skill(skill_name="summarization", description="Summarizes text")
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)

    assert skill.id is not None
    assert skill.skill_name == "summarization"
    assert skill.skill_selected_freq == 0


async def test_skill_name_must_be_unique(db_session, sample_skill):
    duplicate = Skill(skill_name=sample_skill.skill_name, description="Another description")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_skill_repr(sample_skill):
    assert repr(sample_skill) == f"<Skill id={sample_skill.id} name={sample_skill.skill_name}>"


async def test_tool_creation(db_session):
    tool = ToolDefinition(tool_name="web_search", description="Searches the web")
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    assert tool.id is not None
    assert tool.tool_name == "web_search"
    assert tool.tool_selected_freq == 0


async def test_tool_name_must_be_unique(db_session, sample_tool):
    duplicate = ToolDefinition(tool_name=sample_tool.tool_name, description="Another description")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_tool_repr(sample_tool):
    assert repr(sample_tool) == f"<ToolDefinition id={sample_tool.id} name={sample_tool.tool_name}>"


async def test_agent_profile_creation(db_session):
    agent = AgentProfile(agent_name="assistant", description="A helpful assistant")
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    assert agent.id is not None
    assert agent.agent_name == "assistant"


async def test_agent_profile_name_must_be_unique(db_session, sample_agent_profile):
    duplicate = AgentProfile(agent_name=sample_agent_profile.agent_name, description="Another description")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_agent_profile_repr(sample_agent_profile):
    assert repr(sample_agent_profile) == f"<AgentProfile id={sample_agent_profile.id} name={sample_agent_profile.agent_name}>"


async def test_agent_profile_skills_relationship(db_session, sample_agent_profile, sample_skill):
    sample_agent_profile.skills.append(sample_skill)
    db_session.add(sample_agent_profile)
    await db_session.commit()
    await db_session.refresh(sample_agent_profile)

    assert sample_skill in sample_agent_profile.skills
    assert sample_agent_profile in sample_skill.agent_profiles


async def test_agent_profile_tools_relationship(db_session, sample_agent_profile, sample_tool):
    sample_agent_profile.tools.append(sample_tool)
    db_session.add(sample_agent_profile)
    await db_session.commit()
    await db_session.refresh(sample_agent_profile)

    assert sample_tool in sample_agent_profile.tools
    assert sample_agent_profile in sample_tool.agent_profiles


async def test_config_bundle_creation(db_session, sample_user, sample_agent_profile):
    bundle = ConfigBundle(
        user_id=sample_user.id,
        agent_id=sample_agent_profile.id,
        name="default-bundle",
        description="Default configuration",
    )
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)

    assert bundle.id is not None
    assert bundle.created_at is not None
    assert bundle.user_id == sample_user.id
    assert bundle.agent_id == sample_agent_profile.id


async def test_config_bundle_name_unique_per_user(db_session, sample_config_bundle):
    duplicate = ConfigBundle(
        user_id=sample_config_bundle.user_id,
        agent_id=sample_config_bundle.agent_id,
        name=sample_config_bundle.name,
        description="Another description",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_config_bundle_same_name_allowed_for_different_users(
    db_session, sample_config_bundle, another_user, sample_agent_profile
):
    bundle = ConfigBundle(
        user_id=another_user.id,
        agent_id=sample_agent_profile.id,
        name=sample_config_bundle.name,
        description="Same name, different user",
    )
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)

    assert bundle.id is not None


async def test_config_bundle_user_relationship(db_session, sample_config_bundle, sample_user):
    await db_session.refresh(sample_user, attribute_names=["configs"])
    assert sample_config_bundle in sample_user.configs
    assert sample_config_bundle.user.id == sample_user.id


async def test_config_bundle_skills_relationship(db_session, sample_config_bundle, sample_skill):
    sample_config_bundle.skills.append(sample_skill)
    db_session.add(sample_config_bundle)
    await db_session.commit()
    await db_session.refresh(sample_config_bundle)

    assert sample_skill in sample_config_bundle.skills
    assert sample_config_bundle in sample_skill.config_bundles


async def test_config_bundle_tools_relationship(db_session, sample_config_bundle, sample_tool):
    sample_config_bundle.tools.append(sample_tool)
    db_session.add(sample_config_bundle)
    await db_session.commit()
    await db_session.refresh(sample_config_bundle)

    assert sample_tool in sample_config_bundle.tools
    assert sample_config_bundle in sample_tool.config_bundles


async def test_config_bundle_repr(sample_config_bundle):
    assert repr(sample_config_bundle) == f"<ConfigBundle id={sample_config_bundle.id} name={sample_config_bundle.name}>"


async def test_deleting_user_cascades_config_bundles(db_session, sample_user, sample_config_bundle):
    await db_session.delete(sample_user)
    await db_session.commit()

    result = await db_session.get(ConfigBundle, sample_config_bundle.id, populate_existing=True)
    assert result is None

    
async def test_deleting_agent_profile_cascades_config_bundles(db_session, sample_agent_profile, sample_config_bundle):
    await db_session.delete(sample_agent_profile)
    await db_session.commit()

    result = await db_session.get(ConfigBundle, sample_config_bundle.id, populate_existing=True)
    assert result is None


async def test_token_usage_event_creation(db_session, sample_user, sample_agent_profile):
    event = TokenUsageEvent(
        user_id=sample_user.id,
        agent_id=sample_agent_profile.id,
        tokens_used=250,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    assert event.id is not None
    assert event.tokens_used == 250
    assert event.reported_at is not None


async def test_token_usage_event_agent_id_is_nullable(db_session, sample_user):
    event = TokenUsageEvent(user_id=sample_user.id, agent_id=None, tokens_used=100)
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    assert event.agent_id is None


async def test_token_usage_event_user_relationship(db_session, sample_token_usage_event, sample_user):
    await db_session.refresh(sample_user, attribute_names=["token_usage_events"])
    assert sample_token_usage_event in sample_user.token_usage_events
    assert sample_token_usage_event.user.id == sample_user.id


async def test_deleting_user_cascades_token_usage_events(db_session, sample_user, sample_token_usage_event):
    await db_session.delete(sample_user)
    await db_session.commit()

    result = await db_session.get(TokenUsageEvent, sample_token_usage_event.id, populate_existing=True)
    assert result is None

async def test_device_code_creation(db_session, sample_user):
    from datetime import datetime, timedelta, timezone

    device_code = DeviceCode(
        device_code="XYZ1-2345",
        user_id=sample_user.id,
        scope="read write",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        interval=5,
    )
    db_session.add(device_code)
    await db_session.commit()
    await db_session.refresh(device_code)

    assert device_code.id is not None
    assert device_code.status == DeviceStatus.PENDING


async def test_device_code_value_must_be_unique(db_session, sample_device_code):
    from datetime import datetime, timedelta, timezone

    duplicate = DeviceCode(
        device_code=sample_device_code.device_code,
        user_id=sample_device_code.user_id,
        scope="read",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        interval=5,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_device_code_status_transition(db_session, sample_device_code):
    sample_device_code.status = DeviceStatus.APPROVED
    db_session.add(sample_device_code)
    await db_session.commit()
    await db_session.refresh(sample_device_code)

    assert sample_device_code.status == DeviceStatus.APPROVED


async def test_device_code_repr(sample_device_code):
    text = repr(sample_device_code)
    assert "DeviceCode" in text
    assert sample_device_code.device_code in text


async def test_agent_profile_skill_link_row_exists(db_session, sample_agent_profile, sample_skill):
    sample_agent_profile.skills.append(sample_skill)
    db_session.add(sample_agent_profile)
    await db_session.commit()

    link = await db_session.get(AgentProfileSkill, (sample_agent_profile.id, sample_skill.id))
    assert link is not None


async def test_agent_profile_tool_link_row_exists(db_session, sample_agent_profile, sample_tool):
    sample_agent_profile.tools.append(sample_tool)
    db_session.add(sample_agent_profile)
    await db_session.commit()

    link = await db_session.get(AgentProfileTool, (sample_agent_profile.id, sample_tool.id))
    assert link is not None


async def test_config_bundle_skill_link_row_exists(db_session, sample_config_bundle, sample_skill):
    sample_config_bundle.skills.append(sample_skill)
    db_session.add(sample_config_bundle)
    await db_session.commit()

    link = await db_session.get(ConfigBundleSkill, (sample_config_bundle.id, sample_skill.id))
    assert link is not None


async def test_config_bundle_tool_link_row_exists(db_session, sample_config_bundle, sample_tool):
    sample_config_bundle.tools.append(sample_tool)
    db_session.add(sample_config_bundle)
    await db_session.commit()

    link = await db_session.get(ConfigBundleTool, (sample_config_bundle.id, sample_tool.id))
    assert link is not None


async def test_deleting_agent_profile_cascades_skill_links(db_session, sample_agent_profile, sample_skill):
    sample_agent_profile.skills.append(sample_skill)
    db_session.add(sample_agent_profile)
    await db_session.commit()

    agent_id, skill_id = sample_agent_profile.id, sample_skill.id
    await db_session.delete(sample_agent_profile)
    await db_session.commit()

    link = await db_session.get(AgentProfileSkill, (agent_id, skill_id))
    assert link is None

    remaining_skill = await db_session.get(Skill, skill_id)
    assert remaining_skill is not None