import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.db.models.agent_profile_skills import AgentProfileSkill
from src.db.models.agent_profile_tools import AgentProfileTool
from src.db.models.config_bundles import ConfigBundle
from src.db.models.skills import Skill
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.skill_repo import SkillRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def agent_repo(db_session):
    return AgentProfileRepository(db_session)


@pytest.fixture
def reload(db_session, agent_repo):
    async def _reload(agent_id: int):
        db_session.expunge_all()
        return await agent_repo.admin_get_by_id(agent_id)

    return _reload


async def count_skill_links(session, agent_id, skill_id) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(AgentProfileSkill)
        .where(
            AgentProfileSkill.agent_id == agent_id,
            AgentProfileSkill.skill_id == skill_id,
        )
    )
    return result.scalar_one()


async def count_tool_links(session, agent_id, tool_id) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(AgentProfileTool)
        .where(
            AgentProfileTool.agent_id == agent_id,
            AgentProfileTool.tool_id == tool_id,
        )
    )
    return result.scalar_one()


class TestAgentProfileUniqueConstraints:

    async def test_cannot_create_two_agents_with_same_name(self, agent_repo, db_session):
        await agent_repo.create(agent_name="duplicate-agent", description="First")
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await agent_repo.create(agent_name="duplicate-agent", description="Second")
            await db_session.commit()

        await db_session.rollback()


class TestAgentProfileSkillAssociation:

    async def test_add_skill_is_persisted(
        self, agent_repo, db_session, reload, sample_agent_profile, sample_skill
    ):
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        reloaded = await reload(sample_agent_profile.id)

        assert {s.id for s in reloaded.skills} == {sample_skill.id}

    async def test_adding_same_skill_twice_creates_one_link_row(
        self, agent_repo, db_session, sample_agent_profile, sample_skill
    ):
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        assert await count_skill_links(
            db_session, sample_agent_profile.id, sample_skill.id
        ) == 1

    async def test_remove_skill_is_persisted(
        self, agent_repo, db_session, reload, sample_agent_profile, sample_skill
    ):
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        await agent_repo.remove_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        reloaded = await reload(sample_agent_profile.id)

        assert sample_skill.id not in {s.id for s in reloaded.skills}
        assert await count_skill_links(
            db_session, sample_agent_profile.id, sample_skill.id
        ) == 0

    async def test_deleting_agent_removes_links_but_not_skill(
        self, agent_repo, db_session, sample_agent_profile, sample_skill
    ):
        agent_id, skill_id = sample_agent_profile.id, sample_skill.id
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        await agent_repo.delete(sample_agent_profile)
        await db_session.commit()

        assert await count_skill_links(db_session, agent_id, skill_id) == 0
        result = await db_session.execute(
            select(Skill)
            .where(Skill.id == skill_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is not None

    async def test_skill_linked_to_agent_cannot_be_deleted(
        self, agent_repo, db_session, sample_agent_profile, sample_skill
    ):
        agent_id, skill_id = sample_agent_profile.id, sample_skill.id
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await SkillRepository(db_session).delete(sample_skill)
            await db_session.commit()

        await db_session.rollback()

        assert await count_skill_links(db_session, agent_id, skill_id) == 1

    async def test_skill_can_be_deleted_after_unlinking_from_agent(
        self, agent_repo, db_session, reload, sample_agent_profile, sample_skill
    ):
        agent_id, skill_id = sample_agent_profile.id, sample_skill.id
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()
        await agent_repo.remove_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        await SkillRepository(db_session).delete(sample_skill)
        await db_session.commit()

        reloaded = await reload(agent_id)

        assert skill_id not in {s.id for s in reloaded.skills}


class TestAgentProfileToolAssociation:

    async def test_add_tool_is_persisted(
        self, agent_repo, db_session, reload, sample_agent_profile, sample_tool
    ):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await db_session.commit()

        reloaded = await reload(sample_agent_profile.id)

        assert {t.id for t in reloaded.tools} == {sample_tool.id}

    async def test_adding_same_tool_twice_creates_one_link_row(
        self, agent_repo, db_session, sample_agent_profile, sample_tool
    ):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await db_session.commit()

        assert await count_tool_links(
            db_session, sample_agent_profile.id, sample_tool.id
        ) == 1

    async def test_remove_tool_is_persisted(
        self, agent_repo, db_session, reload, sample_agent_profile, sample_tool
    ):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await db_session.commit()

        await agent_repo.remove_tool(sample_agent_profile, sample_tool)
        await db_session.commit()

        reloaded = await reload(sample_agent_profile.id)

        assert sample_tool.id not in {t.id for t in reloaded.tools}

    async def test_adding_multiple_tools_all_persisted(
        self, agent_repo, db_session, reload, sample_agent_profile, sample_tool, another_tool
    ):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await agent_repo.add_tool(sample_agent_profile, another_tool)
        await db_session.commit()

        reloaded = await reload(sample_agent_profile.id)

        assert {t.id for t in reloaded.tools} == {sample_tool.id, another_tool.id}


class TestAgentProfileArchive:

    async def test_archive_is_persisted_and_hides_from_active_queries(
        self, agent_repo, db_session, sample_agent_profile
    ):
        agent_id = sample_agent_profile.id

        await agent_repo.archive(sample_agent_profile)
        await db_session.commit()
        db_session.expunge_all()

        assert await agent_repo.get_active(agent_id) is None
        assert agent_id not in {a.id for a in await agent_repo.list_active()}
        assert (await agent_repo.admin_get_by_id(agent_id)).archived_at is not None

    async def test_restore_is_persisted(
        self, agent_repo, db_session, sample_agent_profile
    ):
        agent_id = sample_agent_profile.id
        await agent_repo.archive(sample_agent_profile)
        await db_session.commit()

        await agent_repo.restore(sample_agent_profile)
        await db_session.commit()
        db_session.expunge_all()

        assert (await agent_repo.get_active(agent_id)).id == agent_id


class TestAgentProfileDeleteBehaviour:

    async def test_agent_with_config_bundles_cannot_be_deleted(
        self, agent_repo, db_session, sample_agent_profile, sample_user, make_bundle
    ):
        bundle = await make_bundle(sample_user, sample_agent_profile)
        bundle_id = bundle.id

        with pytest.raises(IntegrityError):
            await agent_repo.delete(sample_agent_profile)
            await db_session.commit()

        await db_session.rollback()

        result = await db_session.execute(
            select(ConfigBundle)
            .where(ConfigBundle.id == bundle_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is not None

    async def test_agent_can_be_deleted_after_its_bundles_are_removed(
        self, agent_repo, db_session, sample_agent_profile, sample_user, make_bundle
    ):
        agent_id = sample_agent_profile.id
        bundle = await make_bundle(sample_user, sample_agent_profile)
        await db_session.delete(bundle)
        await db_session.commit()

        await agent_repo.delete(sample_agent_profile)
        await db_session.commit()

        db_session.expunge_all()
        assert await agent_repo.admin_get_by_id(agent_id) is None