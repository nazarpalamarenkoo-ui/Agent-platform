import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.db.models.config_bundle_knowledge_packs import ConfigBundleKnowledgePack
from src.db.models.config_bundle_skills import ConfigBundleSkill
from src.db.models.config_bunlde_tools import ConfigBundleTool
from src.db.models.knowledge_packs import KnowledgePack
from src.db.models.skills import Skill
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.skill_repo import SkillRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def config_repo(db_session):
    return ConfigBundleRepository(db_session)


@pytest.fixture
def reload(db_session, config_repo):
    async def _reload(bundle_id: int):
        db_session.expunge_all()
        return await config_repo.get_unscoped_with_relations(bundle_id)

    return _reload


async def count_rows(session, model, *conditions) -> int:
    result = await session.execute(
        select(func.count()).select_from(model).where(*conditions)
    )
    return result.scalar_one()


class TestConfigBundleSkillAssociation:

    async def test_add_skill_is_persisted(
        self, config_repo, db_session, reload, sample_config_bundle, sample_skill
    ):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        reloaded = await reload(sample_config_bundle.id)

        assert {s.id for s in reloaded.skills} == {sample_skill.id}

    async def test_adding_same_skill_twice_creates_one_link_row(
        self, config_repo, db_session, sample_config_bundle, sample_skill
    ):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        assert await count_rows(
            db_session, ConfigBundleSkill,
            ConfigBundleSkill.config_bundle_id == sample_config_bundle.id,
            ConfigBundleSkill.skill_id == sample_skill.id,
        ) == 1

    async def test_remove_skill_is_persisted(
        self, config_repo, db_session, reload, sample_config_bundle, sample_skill
    ):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        await config_repo.remove_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        reloaded = await reload(sample_config_bundle.id)

        assert sample_skill.id not in {s.id for s in reloaded.skills}

    async def test_skill_linked_to_bundle_cannot_be_deleted(
        self, config_repo, db_session, sample_config_bundle, sample_skill
    ):
        bundle_id, skill_id = sample_config_bundle.id, sample_skill.id
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await SkillRepository(db_session).delete(sample_skill)
            await db_session.commit()

        await db_session.rollback()

        assert await count_rows(
            db_session, ConfigBundleSkill,
            ConfigBundleSkill.config_bundle_id == bundle_id,
            ConfigBundleSkill.skill_id == skill_id,
        ) == 1

    async def test_skill_can_be_deleted_after_unlinking_from_bundle(
        self, config_repo, db_session, reload, sample_config_bundle, sample_skill
    ):
        bundle_id, skill_id = sample_config_bundle.id, sample_skill.id
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await db_session.commit()
        await config_repo.remove_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        await SkillRepository(db_session).delete(sample_skill)
        await db_session.commit()

        result = await db_session.execute(
            select(Skill).where(Skill.id == skill_id).execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is None
        reloaded = await reload(bundle_id)
        assert skill_id not in {s.id for s in reloaded.skills}


class TestConfigBundleToolAssociation:

    async def test_add_tool_is_persisted(
        self, config_repo, db_session, reload, sample_config_bundle, sample_tool
    ):
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await db_session.commit()

        reloaded = await reload(sample_config_bundle.id)

        assert {t.id for t in reloaded.tools} == {sample_tool.id}

    async def test_adding_same_tool_twice_creates_one_link_row(
        self, config_repo, db_session, sample_config_bundle, sample_tool
    ):
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await db_session.commit()

        assert await count_rows(
            db_session, ConfigBundleTool,
            ConfigBundleTool.config_bundle_id == sample_config_bundle.id,
            ConfigBundleTool.tool_id == sample_tool.id,
        ) == 1

    async def test_remove_tool_is_persisted(
        self, config_repo, db_session, reload, sample_config_bundle, sample_tool
    ):
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await db_session.commit()

        await config_repo.remove_tool(sample_config_bundle, sample_tool)
        await db_session.commit()

        reloaded = await reload(sample_config_bundle.id)

        assert sample_tool.id not in {t.id for t in reloaded.tools}

    async def test_adding_multiple_tools_and_skills_all_persisted(
        self, config_repo, db_session, reload, sample_config_bundle,
        sample_skill, another_skill, sample_tool, another_tool
    ):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await config_repo.add_skill(sample_config_bundle, another_skill)
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await config_repo.add_tool(sample_config_bundle, another_tool)
        await db_session.commit()

        reloaded = await reload(sample_config_bundle.id)

        assert {s.id for s in reloaded.skills} == {sample_skill.id, another_skill.id}
        assert {t.id for t in reloaded.tools} == {sample_tool.id, another_tool.id}


class TestConfigBundleKnowledgePackAssociation:

    async def test_add_knowledge_pack_is_persisted(
        self, config_repo, db_session, reload, sample_config_bundle, sample_knowledge_pack
    ):
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await db_session.commit()

        reloaded = await reload(sample_config_bundle.id)

        assert {p.id for p in reloaded.knowledge_packs} == {sample_knowledge_pack.id}

    async def test_adding_same_pack_twice_creates_one_link_row(
        self, config_repo, db_session, sample_config_bundle, sample_knowledge_pack
    ):
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await db_session.commit()

        assert await count_rows(
            db_session, ConfigBundleKnowledgePack,
            ConfigBundleKnowledgePack.config_bundle_id == sample_config_bundle.id,
            ConfigBundleKnowledgePack.knowledge_pack_id == sample_knowledge_pack.id,
        ) == 1

    async def test_remove_knowledge_pack_is_persisted(
        self, config_repo, db_session, reload, sample_config_bundle, sample_knowledge_pack
    ):
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await db_session.commit()

        await config_repo.remove_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await db_session.commit()

        reloaded = await reload(sample_config_bundle.id)

        assert sample_knowledge_pack.id not in {p.id for p in reloaded.knowledge_packs}

    async def test_knowledge_pack_linked_to_bundle_cannot_be_deleted(
        self, config_repo, db_session, sample_config_bundle, sample_knowledge_pack
    ):
        bundle_id, pack_id = sample_config_bundle.id, sample_knowledge_pack.id
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await db_session.commit()

        with pytest.raises(IntegrityError):
            pack = await db_session.get(KnowledgePack, pack_id)
            await db_session.delete(pack)
            await db_session.commit()

        await db_session.rollback()

        assert await count_rows(
            db_session, ConfigBundleKnowledgePack,
            ConfigBundleKnowledgePack.config_bundle_id == bundle_id,
            ConfigBundleKnowledgePack.knowledge_pack_id == pack_id,
        ) == 1

    async def test_knowledge_pack_can_be_deleted_after_unlinking_from_bundle(
        self, config_repo, db_session, reload, sample_config_bundle, sample_knowledge_pack
    ):
        bundle_id, pack_id = sample_config_bundle.id, sample_knowledge_pack.id
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await db_session.commit()
        await config_repo.remove_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await db_session.commit()

        pack = await db_session.get(KnowledgePack, pack_id)
        await db_session.delete(pack)
        await db_session.commit()

        reloaded = await reload(bundle_id)

        assert pack_id not in {p.id for p in reloaded.knowledge_packs}


class TestConfigBundleDelete:

    async def test_deleting_bundle_removes_links_but_not_linked_items(
        self, config_repo, db_session, sample_config_bundle,
        sample_skill, sample_tool, sample_knowledge_pack
    ):
        bundle_id = sample_config_bundle.id
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await db_session.commit()

        await config_repo.delete(sample_config_bundle)
        await db_session.commit()

        assert await count_rows(
            db_session, ConfigBundleSkill, ConfigBundleSkill.config_bundle_id == bundle_id
        ) == 0
        assert await count_rows(
            db_session, ConfigBundleTool, ConfigBundleTool.config_bundle_id == bundle_id
        ) == 0
        assert await count_rows(
            db_session, ConfigBundleKnowledgePack,
            ConfigBundleKnowledgePack.config_bundle_id == bundle_id,
        ) == 0
        assert await count_rows(db_session, Skill, Skill.id == sample_skill.id) == 1
        assert await count_rows(
            db_session, KnowledgePack, KnowledgePack.id == sample_knowledge_pack.id
        ) == 1


class TestConfigBundleGetForUserAndAgent:

    async def test_returns_all_bundles_for_user_agent_pair(
        self, config_repo, make_user, make_agent, make_bundle
    ):
        user, agent = await make_user(), await make_agent()
        bundle_a = await make_bundle(user, agent)
        bundle_b = await make_bundle(user, agent)

        results = await config_repo.get_for_user_and_agent(user.id, agent.id)

        assert {c.id for c in results} == {bundle_a.id, bundle_b.id}

    async def test_does_not_return_bundles_of_other_user(
        self, config_repo, make_user, make_agent, make_bundle
    ):
        user, other, agent = await make_user(), await make_user(), await make_agent()
        theirs = await make_bundle(other, agent)

        results = await config_repo.get_for_user_and_agent(user.id, agent.id)

        assert theirs.id not in {c.id for c in results}


class TestUsersAffectedReflectCommittedLinks:

    async def test_user_stops_being_affected_after_skill_is_removed(
        self, config_repo, db_session, sample_config_bundle, sample_user, sample_skill
    ):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await db_session.commit()
        assert await config_repo.list_user_ids_with_skill(sample_skill.id) == [sample_user.id]

        await config_repo.remove_skill(sample_config_bundle, sample_skill)
        await db_session.commit()

        assert await config_repo.list_user_ids_with_skill(sample_skill.id) == []

    async def test_user_is_affected_via_profile_after_commit(
        self, db_session, config_repo, sample_config_bundle,
        sample_agent_profile, sample_user, sample_tool
    ):
        sample_agent_profile.tools.append(sample_tool)
        await db_session.commit()

        assert await config_repo.list_user_ids_with_tool(sample_tool.id) == [sample_user.id]