import itertools
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, InvalidRequestError

from src.db.enums.notification_type import NotificationType
from src.db.enums.skill_visibility import SkillVisibility
from src.db.enums.tool_visibility import ToolVisibility
from src.db.enums.user_role import UserRole
from src.db.models.agent_profiles import AgentProfile
from src.db.models.background_jobs import BackgroundJob
from src.db.models.config_bundles import ConfigBundle
from src.db.models.device_code import DeviceCode
from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.knowledge_packs import KnowledgePack
from src.db.models.notification import Notification
from src.db.models.skill_access_logs import SkillAccessLog
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition
from src.db.models.users import User

pytestmark = pytest.mark.integration

_counter = itertools.count(1)


def make_user(**overrides) -> User:
    n = next(_counter)
    values = dict(
        username=f"user-{n}",
        email=f"user-{n}@example.com",
        password_hash="hashed",
    )
    values.update(overrides)
    return User(**values)


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


def make_private_skill(owner: User, **overrides) -> Skill:
    return make_skill(owner_id=owner.id, visibility=SkillVisibility.PRIVATE, **overrides)


def make_private_tool(owner: User, **overrides) -> ToolDefinition:
    return make_tool(owner_id=owner.id, visibility=ToolVisibility.PRIVATE, **overrides)


def make_bundle(user: User, agent: AgentProfile, **overrides) -> ConfigBundle:
    n = next(_counter)
    values = dict(
        user_id=user.id,
        agent_id=agent.id,
        name=f"bundle-{n}",
        description="desc",
    )
    values.update(overrides)
    return ConfigBundle(**values)


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


async def fetch(session, model, pk):
    return await session.get(model, pk, populate_existing=True)


async def assert_commit_fails(session, exc=IntegrityError):
    with pytest.raises(exc):
        await session.commit()
    await session.rollback()


class TestDeletingUser:

    async def test_removes_everything_the_user_owns(self, db_session, sample_agent_profile):
        owner = await persist(db_session, make_user())
        skill = await persist(db_session, make_private_skill(owner))
        tool = await persist(db_session, make_private_tool(owner))
        bundle = await persist(db_session, make_bundle(owner, sample_agent_profile))
        bundle.skills.append(skill)
        bundle.tools.append(tool)
        await db_session.commit()

        device = await persist(db_session, make_device(owner.id, config_bundle_id=bundle.id))
        notification = await persist(
            db_session,
            Notification(user_id=owner.id, type=NotificationType.SKILL_ARCHIVED, skill_id=skill.id),
        )
        log = await persist(
            db_session,
            SkillAccessLog(owner_id=owner.id, skill_id=skill.id, action="view"),
        )
        job = await persist(
            db_session,
            BackgroundJob(job_type="discovery_ingest", user_id=owner.id),
        )

        ids = {
            Skill: skill.id,
            ToolDefinition: tool.id,
            ConfigBundle: bundle.id,
            DeviceCode: device.id,
            Notification: notification.id,
            SkillAccessLog: log.id,
        }
        job_id = job.id

        await db_session.delete(owner)
        await db_session.commit()

        for model, pk in ids.items():
            assert await fetch(db_session, model, pk) is None, model.__name__

        surviving_job = await fetch(db_session, BackgroundJob, job_id)
        assert surviving_job is not None
        assert surviving_job.user_id is None

    async def test_does_not_touch_global_content_or_other_users_data(
        self, db_session, sample_agent_profile, another_user
    ):
        owner = await persist(db_session, make_user())
        global_skill = await persist(db_session, make_skill())
        global_tool = await persist(db_session, make_tool())
        other_skill = await persist(db_session, make_private_skill(another_user))
        other_bundle = await persist(db_session, make_bundle(another_user, sample_agent_profile))
        other_bundle.skills.append(global_skill)
        other_bundle.tools.append(global_tool)
        await db_session.commit()

        await persist(db_session, make_bundle(owner, sample_agent_profile))

        await db_session.delete(owner)
        await db_session.commit()

        assert await fetch(db_session, Skill, global_skill.id) is not None
        assert await fetch(db_session, ToolDefinition, global_tool.id) is not None
        assert await fetch(db_session, Skill, other_skill.id) is not None
        reloaded = await fetch(db_session, ConfigBundle, other_bundle.id)
        assert {s.id for s in reloaded.skills} == {global_skill.id}
        assert {t.id for t in reloaded.tools} == {global_tool.id}

    async def test_succeeds_when_private_skill_is_used_only_in_own_bundle(
        self, db_session, sample_agent_profile
    ):
        owner = await persist(db_session, make_user())
        skill = await persist(db_session, make_private_skill(owner))
        bundle = await persist(db_session, make_bundle(owner, sample_agent_profile))
        bundle.skills.append(skill)
        await db_session.commit()
        skill_id, bundle_id = skill.id, bundle.id

        await db_session.delete(owner)
        await db_session.commit()

        assert await fetch(db_session, Skill, skill_id) is None
        assert await fetch(db_session, ConfigBundle, bundle_id) is None

    async def test_is_blocked_when_private_skill_is_used_by_agent_profile(
        self, db_session, sample_agent_profile
    ):
        owner = await persist(db_session, make_user())
        skill = await persist(db_session, make_private_skill(owner))
        sample_agent_profile.skills.append(skill)
        await db_session.commit()

        await db_session.delete(owner)
        await assert_commit_fails(db_session)

    async def test_is_blocked_when_private_skill_is_used_in_another_users_bundle(
        self, db_session, sample_agent_profile, another_user
    ):
        owner = await persist(db_session, make_user())
        skill = await persist(db_session, make_private_skill(owner))
        foreign_bundle = await persist(db_session, make_bundle(another_user, sample_agent_profile))
        foreign_bundle.skills.append(skill)
        await db_session.commit()

        await db_session.delete(owner)
        await assert_commit_fails(db_session)

    async def test_is_blocked_when_private_tool_is_used_by_agent_profile(
        self, db_session, sample_agent_profile
    ):
        owner = await persist(db_session, make_user())
        tool = await persist(db_session, make_private_tool(owner))
        sample_agent_profile.tools.append(tool)
        await db_session.commit()

        await db_session.delete(owner)
        await assert_commit_fails(db_session)


class TestDeletingAgentProfile:

    async def test_is_blocked_while_config_bundles_reference_it(
        self, db_session, sample_user, sample_agent_profile
    ):
        await persist(db_session, make_bundle(sample_user, sample_agent_profile))

        await db_session.delete(sample_agent_profile)
        await assert_commit_fails(db_session)

    async def test_succeeds_after_last_bundle_is_removed_and_keeps_skills(
        self, db_session, sample_user, sample_agent_profile
    ):
        skill = await persist(db_session, make_skill())
        sample_agent_profile.skills.append(skill)
        bundle = await persist(db_session, make_bundle(sample_user, sample_agent_profile))
        await db_session.commit()
        agent_id, skill_id = sample_agent_profile.id, skill.id

        await db_session.delete(bundle)
        await db_session.commit()
        await db_session.delete(sample_agent_profile)
        await db_session.commit()

        assert await fetch(db_session, AgentProfile, agent_id) is None
        assert await fetch(db_session, Skill, skill_id) is not None


class TestKnowledgePackUsedByBundle:

    async def test_pack_in_use_cannot_be_deleted(
        self, db_session, config_bundle_with_knowledge_pack, sample_knowledge_pack
    ):
        await db_session.delete(sample_knowledge_pack)
        await assert_commit_fails(db_session)

    async def test_domain_with_pack_in_use_cannot_be_deleted(
        self, db_session, config_bundle_with_knowledge_pack, sample_knowledge_domain
    ):
        await db_session.delete(sample_knowledge_domain)
        await assert_commit_fails(db_session)

    async def test_domain_is_deleted_with_its_packs_once_pack_is_detached(
        self, db_session, config_bundle_with_knowledge_pack, sample_knowledge_pack, sample_knowledge_domain
    ):
        bundle = config_bundle_with_knowledge_pack
        bundle.knowledge_packs.remove(sample_knowledge_pack)
        await db_session.commit()
        pack_id, domain_id = sample_knowledge_pack.id, sample_knowledge_domain.id

        await db_session.delete(sample_knowledge_domain)
        await db_session.commit()

        assert await fetch(db_session, KnowledgeDomain, domain_id) is None
        assert await fetch(db_session, KnowledgePack, pack_id) is None
        assert await fetch(db_session, ConfigBundle, bundle.id) is not None


class TestArchivedNamesStayReserved:

    @pytest.mark.parametrize(
        "factory, name_field",
        [(make_skill, "skill_name"), (make_tool, "tool_name")],
        ids=["skill", "tool"],
    )
    async def test_archived_global_item_still_blocks_its_name(
        self, db_session, factory, name_field
    ):
        await persist(
            db_session,
            factory(**{name_field: "reserved", "archived_at": datetime.now(timezone.utc)}),
        )

        db_session.add(factory(**{name_field: "reserved"}))
        await assert_commit_fails(db_session)


class TestSuperAdminTransfer:

    async def test_promoting_second_super_admin_in_place_fails(self, db_session):
        await persist(db_session, make_user(role=UserRole.SUPER_ADMIN))
        candidate = await persist(db_session, make_user(role=UserRole.ADMIN))

        candidate.role = UserRole.SUPER_ADMIN
        await assert_commit_fails(db_session)

    async def test_transfer_works_when_old_super_admin_is_demoted_first(self, db_session):
        current = await persist(db_session, make_user(role=UserRole.SUPER_ADMIN))
        successor = await persist(db_session, make_user(role=UserRole.ADMIN))

        current.role = UserRole.ADMIN
        await db_session.flush()
        successor.role = UserRole.SUPER_ADMIN
        await db_session.commit()

        assert (await fetch(db_session, User, current.id)).role == UserRole.ADMIN
        assert (await fetch(db_session, User, successor.id)).role == UserRole.SUPER_ADMIN


class TestLoadingStrategy:

    async def test_bundle_graph_is_fully_loaded_without_lazy_io(
        self, db_session, sample_user, sample_agent_profile, sample_knowledge_pack, sample_knowledge_domain
    ):
        skill = await persist(db_session, make_skill())
        tool = await persist(db_session, make_tool())
        skill.domains.append(sample_knowledge_domain)
        bundle = await persist(db_session, make_bundle(sample_user, sample_agent_profile))
        bundle.skills.append(skill)
        bundle.tools.append(tool)
        bundle.knowledge_packs.append(sample_knowledge_pack)
        await db_session.commit()
        bundle_id = bundle.id
        db_session.expunge_all()

        result = await db_session.execute(select(ConfigBundle).where(ConfigBundle.id == bundle_id))
        loaded = result.scalar_one()

        assert loaded.user.id == sample_user.id
        assert loaded.agent.id == sample_agent_profile.id
        assert [s.id for s in loaded.skills] == [skill.id]
        assert [d.id for d in loaded.skills[0].domains] == [sample_knowledge_domain.id]
        assert [t.id for t in loaded.tools] == [tool.id]
        assert [p.id for p in loaded.knowledge_packs] == [sample_knowledge_pack.id]
        assert loaded.knowledge_packs[0].domain.id == sample_knowledge_domain.id

    @pytest.mark.parametrize(
        "make_instance",
        [
            lambda: make_skill(),
            lambda: make_tool(),
        ],
        ids=["skill", "tool"],
    )
    async def test_reverse_collections_must_be_loaded_explicitly(self, db_session, make_instance):
        instance = await persist(db_session, make_instance())
        db_session.expunge_all()
        model = type(instance)

        result = await db_session.execute(select(model).where(model.id == instance.id))
        loaded = result.scalar_one()

        with pytest.raises(InvalidRequestError):
            loaded.config_bundles
        with pytest.raises(InvalidRequestError):
            loaded.agent_profiles