import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.repositories.agent_profile_repo import AgentProfileRepository
from src.db.models.agent_profiles import AgentProfile

pytestmark = pytest.mark.integration


@pytest.fixture
def agent_repo(db_session):
    return AgentProfileRepository(db_session)


class TestAgentProfileUniqueConstraints:

    async def test_cannot_create_two_agents_with_same_name(
        self, agent_repo, db_session
    ):
        await agent_repo.create(
            agent_name="duplicate-agent",
            description="First",
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await agent_repo.create(
                agent_name="duplicate-agent",
                description="Second",
            )
            await db_session.commit()

        await db_session.rollback()


class TestAgentProfileSkillAssociation:

    async def test_add_skill_is_persisted(
        self, agent_repo, db_session, sample_agent_profile, sample_skill
    ):
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        agent_id = sample_agent_profile.id
        db_session.expire(sample_agent_profile)
        reloaded = await agent_repo.get_by_id(agent_id)

        skill_ids = {s.id for s in reloaded.skills}
        assert sample_skill.id in skill_ids

    async def test_remove_skill_is_persisted(
        self, agent_repo, db_session, sample_agent_profile, sample_skill
    ):
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        await agent_repo.remove_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        agent_id = sample_agent_profile.id
        db_session.expire(sample_agent_profile)
        reloaded = await agent_repo.get_by_id(agent_id)

        skill_ids = {s.id for s in reloaded.skills}
        assert sample_skill.id not in skill_ids

    async def test_deleting_agent_does_not_delete_skill(
        self, agent_repo, db_session, sample_agent_profile, sample_skill
    ):
        from src.db.models.skills import Skill

        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        await agent_repo.delete(sample_agent_profile)
        await db_session.commit()

        result = await db_session.execute(
            select(Skill)
            .where(Skill.id == sample_skill.id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is not None

    async def test_deleting_skill_removes_it_from_agent(
        self, agent_repo, db_session, sample_agent_profile, sample_skill
    ):
        from src.repositories.skill_repo import SkillRepository

        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await db_session.commit()

        skill_repo = SkillRepository(db_session)
        await skill_repo.delete(sample_skill)
        await db_session.commit()

        agent_id = sample_agent_profile.id
        db_session.expire(sample_agent_profile)
        reloaded = await agent_repo.get_by_id(agent_id)

        skill_ids = {s.id for s in reloaded.skills}
        assert sample_skill.id not in skill_ids


class TestAgentProfileToolAssociation:

    async def test_add_tool_is_persisted(
        self, agent_repo, db_session, sample_agent_profile, sample_tool
    ):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await db_session.commit()

        agent_id = sample_agent_profile.id
        db_session.expire(sample_agent_profile)
        reloaded = await agent_repo.get_by_id(agent_id)

        tool_ids = {t.id for t in reloaded.tools}
        assert sample_tool.id in tool_ids

    async def test_remove_tool_is_persisted(
        self, agent_repo, db_session, sample_agent_profile, sample_tool
    ):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await db_session.commit()

        await agent_repo.remove_tool(sample_agent_profile, sample_tool)
        await db_session.commit()

        agent_id = sample_agent_profile.id
        db_session.expire(sample_agent_profile)
        reloaded = await agent_repo.get_by_id(agent_id)

        tool_ids = {t.id for t in reloaded.tools}
        assert sample_tool.id not in tool_ids

    async def test_adding_multiple_tools_all_persisted(
        self, agent_repo, db_session, sample_agent_profile, sample_tool, another_tool
    ):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await agent_repo.add_tool(sample_agent_profile, another_tool)
        await db_session.commit()

        agent_id = sample_agent_profile.id
        db_session.expire(sample_agent_profile)
        reloaded = await agent_repo.get_by_id(agent_id)

        tool_ids = {t.id for t in reloaded.tools}
        assert sample_tool.id in tool_ids
        assert another_tool.id in tool_ids


class TestAgentProfileDeleteBehaviour:

    async def test_deleting_agent_removes_config_bundles(
        self, agent_repo, db_session, sample_agent_profile, sample_user
    ):
        from src.db.models.config_bundles import ConfigBundle

        bundle = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="to-be-orphaned",
            description="Will cascade",
        )
        db_session.add(bundle)
        await db_session.commit()
        bundle_id = bundle.id

        await agent_repo.delete(sample_agent_profile)
        await db_session.commit()

        result = await db_session.execute(
            select(ConfigBundle)
            .where(ConfigBundle.id == bundle_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is None