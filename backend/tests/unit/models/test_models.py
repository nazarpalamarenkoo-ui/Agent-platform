import itertools
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError, StatementError, DBAPIError, IntegrityError, StatementError
from src.catalog.hint.skill_markdown import skill_file_hash
from src.db.enums.job_status import JobStatus as JobStatusEnum
from src.db.enums.job_type import JobType as JobTypeEnum
from src.db.enums.notification_type import NotificationType
from src.db.enums.skill_visibility import SkillVisibility
from src.db.enums.tool_auth_type import ToolAuthType
from src.db.enums.tool_visibility import ToolVisibility
from src.db.enums.user_role import UserRole
from src.db.models.agent_profile_skills import AgentProfileSkill
from src.db.models.agent_profile_tools import AgentProfileTool
from src.db.models.agent_profiles import AgentProfile
from src.db.models.background_jobs import BackgroundJob, JobStatus, JobType
from src.db.models.config_bunlde_tools import ConfigBundleTool
from src.db.models.config_bundle_skills import ConfigBundleSkill
from src.db.models.config_bundles import ConfigBundle
from src.db.models.device_code import DeviceCode
from src.db.models.knowledge_packs import KnowledgePack
from src.db.models.notification import Notification
from src.db.models.skill_access_logs import SkillAccessLog
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition
from src.db.models.users import User

pytestmark = pytest.mark.unit

_counter = itertools.count(1)


def make_skill(**overrides) -> Skill:
    n = next(_counter)
    values = dict(
        skill_name=f"skill-{n}",
        description="desc",
        content="# body",
        visibility=SkillVisibility.GLOBAL,
    )
    values.update(overrides)
    return Skill(**values)


def make_tool(**overrides) -> ToolDefinition:
    n = next(_counter)
    values = dict(
        tool_name=f"tool-{n}",
        description="desc",
        url="https://example.com/mcp",
    )
    values.update(overrides)
    return ToolDefinition(**values)


def make_agent(**overrides) -> AgentProfile:
    n = next(_counter)
    values = dict(agent_name=f"agent-{n}", description="desc")
    values.update(overrides)
    return AgentProfile(**values)


def make_user(**overrides) -> User:
    n = next(_counter)
    values = dict(
        username=f"user-{n}",
        email=f"user-{n}@example.com",
        password_hash="hashed",
    )
    values.update(overrides)
    return User(**values)


def make_device(user_id: int, **overrides) -> DeviceCode:
    n = next(_counter)
    values = dict(
        user_id=user_id,
        name=f"device-{n}",
        token_hash=f"{n:064x}",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    values.update(overrides)
    return DeviceCode(**values)


async def persist(session, *objs):
    session.add_all(objs)
    await session.commit()
    for obj in objs:
        await session.refresh(obj)
    return objs[0] if len(objs) == 1 else objs


async def assert_commit_fails(session, exc=IntegrityError):
    with pytest.raises(exc):
        await session.commit()
    await session.rollback()

async def test_user_role_defaults_to_user(db_session):
    user = await persist(db_session, make_user())

    assert user.role == UserRole.USER
    assert user.is_admin is False
    assert user.is_super_admin is False


@pytest.mark.parametrize(
    "role, is_admin, is_super_admin",
    [
        (UserRole.USER, False, False),
        (UserRole.ADMIN, True, False),
        (UserRole.SUPER_ADMIN, True, True),
    ],
)
async def test_user_role_flags(db_session, role, is_admin, is_super_admin):
    user = await persist(db_session, make_user(role=role))

    assert user.role == role
    assert user.is_admin is is_admin
    assert user.is_super_admin is is_super_admin


async def test_user_only_one_super_admin_allowed(db_session):
    await persist(db_session, make_user(role=UserRole.SUPER_ADMIN))

    db_session.add(make_user(role=UserRole.SUPER_ADMIN))
    await assert_commit_fails(db_session)


async def test_user_multiple_admins_allowed(db_session):
    first, second = await persist(
        db_session,
        make_user(role=UserRole.ADMIN),
        make_user(role=UserRole.ADMIN),
    )

    assert first.id != second.id


async def test_user_invalid_role_is_rejected(db_session):
    db_session.add(make_user(role="root"))
    await assert_commit_fails(db_session, StatementError)


async def test_user_repr_contains_role(db_session):
    user = await persist(db_session, make_user(role=UserRole.ADMIN))

    text = repr(user)
    assert f"id={user.id}" in text
    assert f"username={user.username}" in text
    assert "role=" in text


async def test_agent_profile_defaults(db_session):
    agent = await persist(db_session, make_agent())

    assert agent.is_neutral is False
    assert agent.archived_at is None
    assert agent.is_archived is False
    assert agent.created_at is not None
    assert agent.updated_at is not None
    assert agent.skills == []
    assert agent.tools == []


async def test_agent_profile_is_archived_flag(db_session):
    agent = await persist(db_session, make_agent(archived_at=datetime.now(timezone.utc)))

    assert agent.is_archived is True


async def test_agent_profile_only_one_neutral_allowed(db_session):
    await persist(db_session, make_agent(is_neutral=True))

    db_session.add(make_agent(is_neutral=True))
    await assert_commit_fails(db_session)


async def test_agent_profile_many_non_neutral_allowed(db_session):
    await persist(db_session, make_agent(is_neutral=True))
    first, second = await persist(db_session, make_agent(), make_agent())

    assert first.is_neutral is False
    assert second.is_neutral is False


async def test_agent_profile_description_is_required(db_session):
    db_session.add(AgentProfile(agent_name="no-description", description=None))
    await assert_commit_fails(db_session)


async def test_skill_global_creation(db_session):
    skill = await persist(db_session, make_skill(skill_name="summarization"))

    assert skill.id is not None
    assert skill.owner_id is None
    assert skill.visibility == SkillVisibility.GLOBAL
    assert skill.archived_at is None
    assert skill.is_archived is False
    assert skill.skill_selected_freq == 0
    assert skill.created_at is not None
    assert skill.updated_at is not None
    assert skill.domains == []


async def test_skill_private_skill_with_owner(db_session, sample_user):
    skill = await persist(
        db_session,
        make_skill(owner_id=sample_user.id, visibility=SkillVisibility.PRIVATE),
    )

    assert skill.owner_id == sample_user.id
    assert skill.visibility == SkillVisibility.PRIVATE


async def test_skill_pending_review_with_owner_is_allowed(db_session, sample_user):
    skill = await persist(
        db_session,
        make_skill(owner_id=sample_user.id, visibility=SkillVisibility.PENDING_REVIEW),
    )

    assert skill.visibility == SkillVisibility.PENDING_REVIEW


async def test_skill_global_with_owner_violates_check(db_session, sample_user):
    db_session.add(make_skill(owner_id=sample_user.id, visibility=SkillVisibility.GLOBAL))
    await assert_commit_fails(db_session)


@pytest.mark.parametrize(
    "visibility", [SkillVisibility.PRIVATE, SkillVisibility.PENDING_REVIEW]
)
async def test_skill_non_global_without_owner_violates_check(db_session, visibility):
    db_session.add(make_skill(owner_id=None, visibility=visibility))
    await assert_commit_fails(db_session)


async def test_skill_invalid_visibility_is_rejected(db_session):
    db_session.add(make_skill(visibility="secret"))
    await assert_commit_fails(db_session, StatementError)


async def test_skill_global_name_must_be_unique(db_session):
    await persist(db_session, make_skill(skill_name="dup"))

    db_session.add(make_skill(skill_name="dup"))
    await assert_commit_fails(db_session)


async def test_skill_same_name_unique_per_owner(db_session, sample_user):
    await persist(
        db_session,
        make_skill(skill_name="dup", owner_id=sample_user.id, visibility=SkillVisibility.PRIVATE),
    )

    db_session.add(
        make_skill(skill_name="dup", owner_id=sample_user.id, visibility=SkillVisibility.PRIVATE)
    )
    await assert_commit_fails(db_session)


async def test_skill_same_name_allowed_for_different_owners(db_session, sample_user, another_user):
    first, second = await persist(
        db_session,
        make_skill(skill_name="dup", owner_id=sample_user.id, visibility=SkillVisibility.PRIVATE),
        make_skill(skill_name="dup", owner_id=another_user.id, visibility=SkillVisibility.PRIVATE),
    )

    assert first.id != second.id


async def test_skill_same_name_allowed_for_global_and_private(db_session, sample_user):
    glob, priv = await persist(
        db_session,
        make_skill(skill_name="dup"),
        make_skill(skill_name="dup", owner_id=sample_user.id, visibility=SkillVisibility.PRIVATE),
    )

    assert glob.id != priv.id


async def test_skill_archived_flag(db_session):
    skill = await persist(db_session, make_skill(archived_at=datetime.now(timezone.utc)))

    assert skill.is_archived is True


async def test_skill_description_is_required(db_session):
    db_session.add(Skill(skill_name="nodesc", description=None, visibility=SkillVisibility.GLOBAL))
    await assert_commit_fails(db_session)


async def test_deleting_owner_cascades_private_skills(db_session):
    owner = await persist(db_session, make_user())
    skill = await persist(
        db_session,
        make_skill(owner_id=owner.id, visibility=SkillVisibility.PRIVATE),
    )
    skill_id = skill.id

    await db_session.delete(owner)
    await db_session.commit()

    assert await db_session.get(Skill, skill_id, populate_existing=True) is None


async def test_skill_repr_contains_visibility(db_session):
    skill = await persist(db_session, make_skill())

    text = repr(skill)
    assert f"id={skill.id}" in text
    assert f"name={skill.skill_name}" in text
    assert "visibility=" in text


async def test_skill_content_hash_is_computed_on_creation(db_session):
    skill = await persist(
        db_session,
        make_skill(skill_name="hashed", description="d", content="body"),
    )

    assert skill.content_hash
    assert skill.content_hash == skill_file_hash("hashed", "d", "body")


async def test_skill_content_hash_without_content(db_session):
    skill = Skill(skill_name="n", description="d")

    assert skill.content_hash == skill_file_hash("n", "d", "")


@pytest.mark.parametrize(
    "field, new_value",
    [
        ("skill_name", "renamed"),
        ("description", "new description"),
        ("content", "new content"),
    ],
)
async def test_skill_content_hash_changes_when_field_changes(db_session, field, new_value):
    skill = await persist(
        db_session,
        make_skill(skill_name="orig", description="d", content="body"),
    )
    old_hash = skill.content_hash

    setattr(skill, field, new_value)
    await db_session.commit()
    await db_session.refresh(skill)

    assert skill.content_hash != old_hash
    assert skill.content_hash == skill_file_hash(
        skill.skill_name, skill.description, skill.content
    )


async def test_skill_content_hash_is_deterministic(db_session):
    first = make_skill(skill_name="same", description="d", content="c")
    second = make_skill(skill_name="same", description="d", content="c")

    assert first.content_hash == second.content_hash


async def test_skill_content_hash_ignores_unrelated_fields(db_session):
    skill = await persist(db_session, make_skill())
    old_hash = skill.content_hash

    skill.skill_selected_freq = 5
    await db_session.commit()
    await db_session.refresh(skill)

    assert skill.content_hash == old_hash

async def test_tool_defaults(db_session):
    tool = await persist(db_session, make_tool(tool_name="web_search"))

    assert tool.id is not None
    assert tool.owner_id is None
    assert tool.visibility == ToolVisibility.GLOBAL
    assert tool.auth_type == ToolAuthType.NONE
    assert tool.auth_description is None
    assert tool.archived_at is None
    assert tool.tool_selected_freq == 0
    assert tool.is_archived is False
    assert tool.is_custom is False
    assert tool.domains == []


async def test_tool_url_is_required(db_session):
    db_session.add(ToolDefinition(tool_name="no-url", description="d", url=None))
    await assert_commit_fails(db_session)


async def test_tool_url_accepts_2048_chars(db_session):
    url = "https://example.com/" + "a" * (2048 - len("https://example.com/"))
    tool = await persist(db_session, make_tool(url=url))

    assert len(tool.url) == 2048


async def test_tool_url_longer_than_2048_chars_is_rejected(db_session):
    db_session.add(make_tool(url="https://example.com/" + "a" * 2048))
    await assert_commit_fails(db_session, DBAPIError)



@pytest.mark.parametrize("auth_type", list(ToolAuthType))
async def test_tool_auth_type_round_trip(db_session, auth_type):
    tool = await persist(
        db_session,
        make_tool(auth_type=auth_type, auth_description="how to auth"),
    )

    assert tool.auth_type is auth_type
    assert tool.auth_description == "how to auth"


async def test_tool_invalid_auth_type_is_rejected(db_session):
    db_session.add(make_tool(auth_type="kerberos"))
    await assert_commit_fails(db_session, StatementError)


async def test_tool_private_with_owner_is_custom(db_session, sample_user):
    tool = await persist(
        db_session,
        make_tool(owner_id=sample_user.id, visibility=ToolVisibility.PRIVATE),
    )

    assert tool.is_custom is True


async def test_tool_global_with_owner_violates_check(db_session, sample_user):
    db_session.add(make_tool(owner_id=sample_user.id, visibility=ToolVisibility.GLOBAL))
    await assert_commit_fails(db_session)


async def test_tool_private_without_owner_violates_check(db_session):
    db_session.add(make_tool(owner_id=None, visibility=ToolVisibility.PRIVATE))
    await assert_commit_fails(db_session)


async def test_tool_global_name_must_be_unique(db_session):
    await persist(db_session, make_tool(tool_name="dup"))

    db_session.add(make_tool(tool_name="dup"))
    await assert_commit_fails(db_session)


async def test_tool_same_name_unique_per_owner(db_session, sample_user):
    await persist(
        db_session,
        make_tool(tool_name="dup", owner_id=sample_user.id, visibility=ToolVisibility.PRIVATE),
    )

    db_session.add(
        make_tool(tool_name="dup", owner_id=sample_user.id, visibility=ToolVisibility.PRIVATE)
    )
    await assert_commit_fails(db_session)


async def test_tool_same_name_allowed_for_different_owners(db_session, sample_user, another_user):
    first, second = await persist(
        db_session,
        make_tool(tool_name="dup", owner_id=sample_user.id, visibility=ToolVisibility.PRIVATE),
        make_tool(tool_name="dup", owner_id=another_user.id, visibility=ToolVisibility.PRIVATE),
    )

    assert first.id != second.id


async def test_tool_same_name_allowed_for_global_and_private(db_session, sample_user):
    glob, priv = await persist(
        db_session,
        make_tool(tool_name="dup"),
        make_tool(tool_name="dup", owner_id=sample_user.id, visibility=ToolVisibility.PRIVATE),
    )

    assert glob.id != priv.id


async def test_tool_archived_flag(db_session):
    tool = await persist(db_session, make_tool(archived_at=datetime.now(timezone.utc)))

    assert tool.is_archived is True


async def test_deleting_owner_cascades_private_tools(db_session):
    owner = await persist(db_session, make_user())
    tool = await persist(
        db_session,
        make_tool(owner_id=owner.id, visibility=ToolVisibility.PRIVATE),
    )
    tool_id = tool.id

    await db_session.delete(owner)
    await db_session.commit()

    assert await db_session.get(ToolDefinition, tool_id, populate_existing=True) is None


async def test_tool_repr(db_session):
    tool = await persist(db_session, make_tool())

    assert repr(tool) == f"<ToolDefinition id={tool.id} name={tool.tool_name}>"


async def test_device_creation(db_session, sample_user):
    device = await persist(db_session, make_device(sample_user.id, name="laptop"))

    assert device.id is not None
    assert device.user_id == sample_user.id
    assert device.name == "laptop"
    assert device.config_bundle_id is None
    assert device.revoked_at is None
    assert device.last_used_at is None
    assert device.created_at is not None
    assert device.expires_at.tzinfo is not None


async def test_device_token_hash_must_be_unique(db_session, sample_user):
    await persist(db_session, make_device(sample_user.id, token_hash="a" * 64))

    db_session.add(make_device(sample_user.id, token_hash="a" * 64))
    await assert_commit_fails(db_session)


@pytest.mark.parametrize("field", ["name", "token_hash", "expires_at", "user_id"])
async def test_device_required_fields_cannot_be_null(db_session, sample_user, field):
    device = make_device(sample_user.id)
    setattr(device, field, None)
    db_session.add(device)
    await assert_commit_fails(db_session)


async def test_device_token_hash_longer_than_64_chars_is_rejected(db_session, sample_user):
    db_session.add(make_device(sample_user.id, token_hash="f" * 65))
    await assert_commit_fails(db_session, DBAPIError)


async def test_device_can_be_revoked_and_marked_used(db_session, sample_user):
    device = await persist(db_session, make_device(sample_user.id))
    now = datetime.now(timezone.utc)

    device.revoked_at = now
    device.last_used_at = now
    await db_session.commit()
    await db_session.refresh(device)

    assert device.revoked_at == now
    assert device.last_used_at == now


async def test_device_can_reference_config_bundle(db_session, sample_user, sample_config_bundle):
    device = await persist(
        db_session,
        make_device(sample_user.id, config_bundle_id=sample_config_bundle.id),
    )

    assert device.config_bundle_id == sample_config_bundle.id


async def test_deleting_config_bundle_sets_device_bundle_null(
    db_session, sample_user, sample_config_bundle
):
    device = await persist(
        db_session,
        make_device(sample_user.id, config_bundle_id=sample_config_bundle.id),
    )

    await db_session.delete(sample_config_bundle)
    await db_session.commit()

    result = await db_session.get(DeviceCode, device.id, populate_existing=True)
    assert result is not None
    assert result.config_bundle_id is None


async def test_deleting_user_cascades_devices(db_session):
    user = await persist(db_session, make_user())
    device = await persist(db_session, make_device(user.id))
    device_id = device.id

    await db_session.delete(user)
    await db_session.commit()

    assert await db_session.get(DeviceCode, device_id, populate_existing=True) is None


async def test_device_repr(db_session, sample_user):
    device = await persist(db_session, make_device(sample_user.id))

    text = repr(device)
    assert f"id={device.id}" in text
    assert f"user_id={device.user_id}" in text
    assert "bundle=None" in text


async def test_knowledge_pack_archived_defaults(sample_knowledge_pack):
    assert sample_knowledge_pack.archived_at is None
    assert sample_knowledge_pack.is_archived is False


async def test_knowledge_pack_is_archived_flag(db_session, sample_knowledge_pack):
    sample_knowledge_pack.archived_at = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(sample_knowledge_pack)

    assert sample_knowledge_pack.is_archived is True


async def test_background_job_defaults(db_session):
    job = await persist(db_session, BackgroundJob(job_type=JobType.DISCOVERY_INGEST.value))

    assert job.id is not None
    assert job.status == JobStatus.PENDING.value
    assert job.payload == {}
    assert job.result is None
    assert job.error is None
    assert job.user_id is None
    assert job.created_at is not None
    assert job.started_at is None
    assert job.finished_at is None


async def test_background_job_jsonb_round_trip(db_session):
    payload = {"urls": ["https://a.example", "https://b.example"], "depth": 2, "nested": {"k": None}}
    result = {"accepted": 1, "rejected": 1}
    job = await persist(
        db_session,
        BackgroundJob(
            job_type=JobType.SKILL_GENERATION.value,
            payload=payload,
            result=result,
        ),
    )

    assert job.payload == payload
    assert job.result == result


async def test_background_job_status_transitions(db_session):
    job = await persist(db_session, BackgroundJob(job_type=JobType.DISCOVERY_INGEST.value))
    started = datetime.now(timezone.utc)

    job.status = JobStatus.RUNNING.value
    job.started_at = started
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == "running"
    assert job.started_at == started

    finished = started + timedelta(seconds=5)
    job.status = JobStatus.FAILED.value
    job.error = "boom"
    job.finished_at = finished
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == "failed"
    assert job.error == "boom"
    assert job.finished_at == finished


async def test_background_job_type_is_required(db_session):
    db_session.add(BackgroundJob(job_type=None))
    await assert_commit_fails(db_session)


async def test_background_job_accepts_arbitrary_type_and_status_strings(db_session):
    job = await persist(
        db_session,
        BackgroundJob(job_type="brand_new_type", status="brand_new_status"),
    )

    assert job.job_type == "brand_new_type"
    assert job.status == "brand_new_status"


async def test_background_job_type_longer_than_50_chars_is_rejected(db_session):
    db_session.add(BackgroundJob(job_type="x" * 51))
    await assert_commit_fails(db_session, DBAPIError)


async def test_background_job_error_is_unbounded_text(db_session):
    long_error = "traceback line\n" * 5000
    job = await persist(
        db_session,
        BackgroundJob(job_type=JobType.DISCOVERY_INGEST.value, error=long_error),
    )

    assert job.error == long_error


async def test_background_job_user_is_optional_and_set_null_on_delete(db_session):
    user = await persist(db_session, make_user())
    job = await persist(
        db_session,
        BackgroundJob(job_type=JobType.DISCOVERY_INGEST.value, user_id=user.id),
    )
    assert job.user_id == user.id

    await db_session.delete(user)
    await db_session.commit()

    result = await db_session.get(BackgroundJob, job.id, populate_existing=True)
    assert result is not None
    assert result.user_id is None


async def test_notification_for_skill(db_session, sample_user):
    skill = await persist(db_session, make_skill())
    notification = await persist(
        db_session,
        Notification(
            user_id=sample_user.id,
            type=NotificationType.SKILL_ARCHIVED,
            skill_id=skill.id,
        ),
    )

    assert notification.id is not None
    assert notification.type == NotificationType.SKILL_ARCHIVED
    assert notification.skill_id == skill.id
    assert notification.tool_id is None
    assert notification.read_at is None
    assert notification.created_at is not None


async def test_notification_for_tool(db_session, sample_user):
    tool = await persist(db_session, make_tool())
    notification = await persist(
        db_session,
        Notification(
            user_id=sample_user.id,
            type=NotificationType.TOOL_ARCHIVED,
            tool_id=tool.id,
        ),
    )

    assert notification.tool_id == tool.id
    assert notification.skill_id is None


async def test_notification_can_be_marked_read(db_session, sample_user):
    skill = await persist(db_session, make_skill())
    notification = await persist(
        db_session,
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED, skill_id=skill.id),
    )
    now = datetime.now(timezone.utc)

    notification.read_at = now
    await db_session.commit()
    await db_session.refresh(notification)

    assert notification.read_at == now


async def test_notification_duplicate_user_type_skill_is_rejected(db_session, sample_user):
    skill = await persist(db_session, make_skill())
    await persist(
        db_session,
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED, skill_id=skill.id),
    )

    db_session.add(
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED, skill_id=skill.id)
    )
    await assert_commit_fails(db_session)


async def test_notification_duplicate_user_type_tool_is_rejected(db_session, sample_user):
    tool = await persist(db_session, make_tool())
    await persist(
        db_session,
        Notification(user_id=sample_user.id, type=NotificationType.TOOL_ARCHIVED, tool_id=tool.id),
    )

    db_session.add(
        Notification(user_id=sample_user.id, type=NotificationType.TOOL_ARCHIVED, tool_id=tool.id)
    )
    await assert_commit_fails(db_session)


async def test_notification_same_skill_allowed_for_different_users(
    db_session, sample_user, another_user
):
    skill = await persist(db_session, make_skill())
    first, second = await persist(
        db_session,
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED, skill_id=skill.id),
        Notification(user_id=another_user.id, type=NotificationType.SKILL_ARCHIVED, skill_id=skill.id),
    )

    assert first.id != second.id


async def test_notification_different_skills_allowed_for_same_user(db_session, sample_user):
    skill_a, skill_b = await persist(db_session, make_skill(), make_skill())
    first, second = await persist(
        db_session,
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED, skill_id=skill_a.id),
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED, skill_id=skill_b.id),
    )

    assert first.id != second.id


async def test_notification_without_skill_or_tool_can_repeat(db_session, sample_user):
    first, second = await persist(
        db_session,
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED),
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED),
    )

    assert first.id != second.id


async def test_notification_invalid_type_is_rejected(db_session, sample_user):
    db_session.add(Notification(user_id=sample_user.id, type="spam"))
    await assert_commit_fails(db_session, StatementError)


@pytest.mark.parametrize("field", ["user_id", "type"])
async def test_notification_required_fields_cannot_be_null(db_session, sample_user, field):
    values = dict(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED)
    values[field] = None
    db_session.add(Notification(**values))
    await assert_commit_fails(db_session)


async def test_deleting_user_cascades_notifications(db_session):
    user = await persist(db_session, make_user())
    notification = await persist(
        db_session,
        Notification(user_id=user.id, type=NotificationType.SKILL_ARCHIVED),
    )
    notification_id = notification.id

    await db_session.delete(user)
    await db_session.commit()

    assert await db_session.get(Notification, notification_id, populate_existing=True) is None


async def test_deleting_skill_cascades_notifications(db_session, sample_user):
    skill = await persist(db_session, make_skill())
    notification = await persist(
        db_session,
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED, skill_id=skill.id),
    )
    notification_id = notification.id

    await db_session.delete(skill)
    await db_session.commit()

    assert await db_session.get(Notification, notification_id, populate_existing=True) is None


async def test_deleting_tool_cascades_notifications(db_session, sample_user):
    tool = await persist(db_session, make_tool())
    notification = await persist(
        db_session,
        Notification(user_id=sample_user.id, type=NotificationType.TOOL_ARCHIVED, tool_id=tool.id),
    )
    notification_id = notification.id

    await db_session.delete(tool)
    await db_session.commit()

    assert await db_session.get(Notification, notification_id, populate_existing=True) is None


async def test_notification_repr(db_session, sample_user):
    notification = await persist(
        db_session,
        Notification(user_id=sample_user.id, type=NotificationType.SKILL_ARCHIVED),
    )

    text = repr(notification)
    assert f"id={notification.id}" in text
    assert f"user_id={sample_user.id}" in text


async def test_skill_access_log_creation(db_session, sample_user, another_user):
    skill = await persist(db_session, make_skill())
    log = await persist(
        db_session,
        SkillAccessLog(
            admin_id=another_user.id,
            owner_id=sample_user.id,
            skill_id=skill.id,
            action="view",
            note="support request",
        ),
    )

    assert log.id is not None
    assert log.admin_id == another_user.id
    assert log.owner_id == sample_user.id
    assert log.skill_id == skill.id
    assert log.action == "view"
    assert log.note == "support request"
    assert log.created_at is not None


async def test_skill_access_log_optional_fields(db_session, sample_user):
    log = await persist(
        db_session,
        SkillAccessLog(owner_id=sample_user.id, action="list"),
    )

    assert log.admin_id is None
    assert log.skill_id is None
    assert log.note is None


@pytest.mark.parametrize("field", ["owner_id", "action"])
async def test_skill_access_log_required_fields_cannot_be_null(db_session, sample_user, field):
    values = dict(owner_id=sample_user.id, action="list")
    values[field] = None
    db_session.add(SkillAccessLog(**values))
    await assert_commit_fails(db_session)


async def test_skill_access_log_action_longer_than_20_chars_is_rejected(db_session, sample_user):
    db_session.add(SkillAccessLog(owner_id=sample_user.id, action="a" * 21))
    await assert_commit_fails(db_session, DBAPIError)


async def test_deleting_admin_sets_admin_id_null(db_session, sample_user):
    admin = await persist(db_session, make_user(role=UserRole.ADMIN))
    log = await persist(
        db_session,
        SkillAccessLog(admin_id=admin.id, owner_id=sample_user.id, action="archive"),
    )

    await db_session.delete(admin)
    await db_session.commit()

    result = await db_session.get(SkillAccessLog, log.id, populate_existing=True)
    assert result is not None
    assert result.admin_id is None


async def test_deleting_owner_cascades_access_logs(db_session, another_user):
    owner = await persist(db_session, make_user())
    log = await persist(
        db_session,
        SkillAccessLog(admin_id=another_user.id, owner_id=owner.id, action="view"),
    )
    log_id = log.id

    await db_session.delete(owner)
    await db_session.commit()

    assert await db_session.get(SkillAccessLog, log_id, populate_existing=True) is None


async def test_deleting_skill_sets_access_log_skill_id_null(db_session, sample_user):
    skill = await persist(db_session, make_skill())
    log = await persist(
        db_session,
        SkillAccessLog(owner_id=sample_user.id, skill_id=skill.id, action="view"),
    )

    await db_session.delete(skill)
    await db_session.commit()

    result = await db_session.get(SkillAccessLog, log.id, populate_existing=True)
    assert result is not None
    assert result.skill_id is None

async def test_agent_profile_skill_duplicate_link_is_rejected(db_session):
    agent, skill = await persist(db_session, make_agent()), await persist(db_session, make_skill())
    await persist(db_session, AgentProfileSkill(agent_id=agent.id, skill_id=skill.id))

    db_session.add(AgentProfileSkill(agent_id=agent.id, skill_id=skill.id))
    await assert_commit_fails(db_session)


async def test_agent_profile_tool_duplicate_link_is_rejected(db_session):
    agent, tool = await persist(db_session, make_agent()), await persist(db_session, make_tool())
    await persist(db_session, AgentProfileTool(agent_id=agent.id, tool_id=tool.id))

    db_session.add(AgentProfileTool(agent_id=agent.id, tool_id=tool.id))
    await assert_commit_fails(db_session)


async def test_config_bundle_skill_duplicate_link_is_rejected(db_session, sample_config_bundle):
    skill = await persist(db_session, make_skill())
    await persist(
        db_session,
        ConfigBundleSkill(config_bundle_id=sample_config_bundle.id, skill_id=skill.id),
    )

    db_session.add(ConfigBundleSkill(config_bundle_id=sample_config_bundle.id, skill_id=skill.id))
    await assert_commit_fails(db_session)


async def test_config_bundle_tool_duplicate_link_is_rejected(db_session, sample_config_bundle):
    tool = await persist(db_session, make_tool())
    await persist(
        db_session,
        ConfigBundleTool(config_bundle_id=sample_config_bundle.id, tool_id=tool.id),
    )

    db_session.add(ConfigBundleTool(config_bundle_id=sample_config_bundle.id, tool_id=tool.id))
    await assert_commit_fails(db_session)


@pytest.mark.parametrize(
    "link_factory",
    [
        lambda a, o: AgentProfileSkill(agent_id=a, skill_id=o),
        lambda a, o: AgentProfileTool(agent_id=a, tool_id=o),
    ],
    ids=["agent-skill", "agent-tool"],
)
async def test_agent_profile_link_with_missing_target_is_rejected(db_session, link_factory):
    agent = await persist(db_session, make_agent())

    db_session.add(link_factory(agent.id, 999_999))
    await assert_commit_fails(db_session)


async def test_deleting_agent_profile_cascades_tool_links_but_not_tool(db_session):
    agent, tool = await persist(db_session, make_agent()), await persist(db_session, make_tool())
    agent.tools.append(tool)
    await db_session.commit()
    agent_id, tool_id = agent.id, tool.id

    await db_session.delete(agent)
    await db_session.commit()

    assert await db_session.get(AgentProfileTool, (agent_id, tool_id)) is None
    assert await db_session.get(ToolDefinition, tool_id) is not None


async def test_deleting_config_bundle_cascades_skill_and_tool_links(
    db_session, sample_config_bundle
):
    skill, tool = await persist(db_session, make_skill()), await persist(db_session, make_tool())
    sample_config_bundle.skills.append(skill)
    sample_config_bundle.tools.append(tool)
    await db_session.commit()
    bundle_id, skill_id, tool_id = sample_config_bundle.id, skill.id, tool.id

    await db_session.delete(sample_config_bundle)
    await db_session.commit()

    assert await db_session.get(ConfigBundleSkill, (bundle_id, skill_id)) is None
    assert await db_session.get(ConfigBundleTool, (bundle_id, tool_id)) is None
    assert await db_session.get(Skill, skill_id) is not None
    assert await db_session.get(ToolDefinition, tool_id) is not None


@pytest.mark.parametrize("target", ["agent_skill", "agent_tool", "bundle_skill", "bundle_tool"])
async def test_deleting_linked_skill_or_tool_is_restricted(
    db_session, sample_config_bundle, target
):
    agent = await persist(db_session, make_agent())
    if target == "agent_skill":
        victim = await persist(db_session, make_skill())
        agent.skills.append(victim)
    elif target == "agent_tool":
        victim = await persist(db_session, make_tool())
        agent.tools.append(victim)
    elif target == "bundle_skill":
        victim = await persist(db_session, make_skill())
        sample_config_bundle.skills.append(victim)
    else:
        victim = await persist(db_session, make_tool())
        sample_config_bundle.tools.append(victim)
    await db_session.commit()

    await db_session.delete(victim)
    await assert_commit_fails(db_session)


async def test_config_bundle_agent_is_restricted_on_delete(db_session, sample_config_bundle):
    """ConfigBundle.agent_id: ondelete=RESTRICT."""
    agent = await db_session.get(AgentProfile, sample_config_bundle.agent_id)

    await db_session.delete(agent)
    await assert_commit_fails(db_session)


@pytest.mark.parametrize(
    "enum_cls, expected",
    [
        (SkillVisibility, {"private", "pending_review", "global"}),
        (ToolVisibility, {"global", "private"}),
        (ToolAuthType, {"none", "api_key", "bearer", "oauth"}),
        (UserRole, {"user", "admin", "super_admin"}),
        (NotificationType, {"skill_archived", "tool_archived"}),
        (JobStatusEnum, {"pending", "running", "done", "failed"}),
        (JobTypeEnum, {"discovery_ingest", "skill_generation", "notify_skill_archived"}),
    ],
)
def test_enum_values(enum_cls, expected):
    assert {member.value for member in enum_cls} == expected


@pytest.mark.parametrize(
    "enum_cls",
    [SkillVisibility, ToolVisibility, ToolAuthType, UserRole, NotificationType, JobStatusEnum, JobTypeEnum],
)
def test_enums_are_str_enums(enum_cls):
    for member in enum_cls:
        assert isinstance(member, str)
        assert member == member.value


def test_job_enums_in_model_module_match_standalone_enums():
    assert {m.name: m.value for m in JobStatus} == {m.name: m.value for m in JobStatusEnum}
    assert {m.name: m.value for m in JobType} == {m.name: m.value for m in JobTypeEnum}