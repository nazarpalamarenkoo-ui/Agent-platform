import pytest
from sqlalchemy import select

from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.db.models.config_bundles import ConfigBundle

pytestmark = pytest.mark.integration


@pytest.fixture
def config_repo(db_session):
    return ConfigBundleRepository(db_session)


class TestConfigBundleSkillAssociation:

    async def test_add_skill_is_persisted(
        self, config_repo, db_session, sample_config_bundle, sample_skill
    ):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        bundle_id = sample_config_bundle.id
        db_session.expire(sample_config_bundle)
        reloaded = await config_repo.get_by_id_with_relations(bundle_id)

        skill_ids = {s.id for s in reloaded.skills}
        assert sample_skill.id in skill_ids

    async def test_remove_skill_is_persisted(
        self, config_repo, db_session, sample_config_bundle, sample_skill
    ):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        await config_repo.remove_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        bundle_id = sample_config_bundle.id
        db_session.expire(sample_config_bundle)
        reloaded = await config_repo.get_by_id_with_relations(bundle_id)

        skill_ids = {s.id for s in reloaded.skills}
        assert sample_skill.id not in skill_ids

    async def test_deleting_skill_removes_it_from_bundle(
        self, config_repo, db_session, sample_config_bundle, sample_skill
    ):
        from src.repositories.skill_repo import SkillRepository
        from src.db.models.skills import Skill

        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        skill_repo = SkillRepository(db_session)
        await skill_repo.delete(sample_skill)
        await db_session.commit()

        result = await db_session.execute(
            select(Skill)
            .where(Skill.id == sample_skill.id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is None

        bundle_id = sample_config_bundle.id
        db_session.expire(sample_config_bundle)
        reloaded = await config_repo.get_by_id_with_relations(bundle_id)
        skill_ids = {s.id for s in reloaded.skills}
        assert sample_skill.id not in skill_ids


class TestConfigBundleToolAssociation:

    async def test_add_tool_is_persisted(
        self, config_repo, db_session, sample_config_bundle, sample_tool
    ):
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await db_session.commit()

        bundle_id = sample_config_bundle.id
        db_session.expire(sample_config_bundle)
        reloaded = await config_repo.get_by_id_with_relations(bundle_id)

        tool_ids = {t.id for t in reloaded.tools}
        assert sample_tool.id in tool_ids

    async def test_remove_tool_is_persisted(
        self, config_repo, db_session, sample_config_bundle, sample_tool
    ):
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await db_session.commit()

        await config_repo.remove_tool(sample_config_bundle, sample_tool)
        await db_session.commit()

        bundle_id = sample_config_bundle.id
        db_session.expire(sample_config_bundle)
        reloaded = await config_repo.get_by_id_with_relations(bundle_id)

        tool_ids = {t.id for t in reloaded.tools}
        assert sample_tool.id not in tool_ids

    async def test_adding_multiple_tools_and_skills_all_persisted(
        self, config_repo, db_session, sample_config_bundle,
        sample_skill, another_skill, sample_tool, another_tool
    ):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await config_repo.add_skill(sample_config_bundle, another_skill)
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await config_repo.add_tool(sample_config_bundle, another_tool)
        await db_session.commit()

        bundle_id = sample_config_bundle.id
        db_session.expire(sample_config_bundle)
        reloaded = await config_repo.get_by_id_with_relations(bundle_id)

        skill_ids = {s.id for s in reloaded.skills}
        tool_ids = {t.id for t in reloaded.tools}

        assert sample_skill.id in skill_ids
        assert another_skill.id in skill_ids
        assert sample_tool.id in tool_ids
        assert another_tool.id in tool_ids


class TestConfigBundleGetForUserAndAgent:

    async def test_returns_all_bundles_for_user_agent_pair(
        self, config_repo, db_session, sample_user, sample_agent_profile
    ):
        bundle_a = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="bundle-alpha",
            description="First bundle",
        )
        bundle_b = ConfigBundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="bundle-beta",
            description="Second bundle",
        )
        db_session.add_all([bundle_a, bundle_b])
        await db_session.commit()

        results = await config_repo.get_for_user_and_agent(
            sample_user.id, sample_agent_profile.id
        )

        ids = {c.id for c in results}
        assert bundle_a.id in ids
        assert bundle_b.id in ids

    async def test_does_not_return_bundles_of_other_user(
        self, config_repo, db_session, sample_user, another_user, sample_agent_profile
    ):
        bundle = ConfigBundle(
            user_id=another_user.id,
            agent_id=sample_agent_profile.id,
            name="other-user-bundle",
            description="Belongs to another user",
        )
        db_session.add(bundle)
        await db_session.commit()

        results = await config_repo.get_for_user_and_agent(
            sample_user.id, sample_agent_profile.id
        )

        ids = {c.id for c in results}
        assert bundle.id not in ids