import pytest

from src.repositories.config_bundle_repo import ConfigBundleRepository

pytestmark = pytest.mark.db


@pytest.fixture
def config_repo(db_session):
    return ConfigBundleRepository(db_session)


class TestLookups:

    async def test_get_owned_checks_owner(
        self, config_repo, make_user, make_agent, make_bundle
    ):
        owner = await make_user()
        other = await make_user()
        bundle = await make_bundle(owner, await make_agent())

        assert (await config_repo.get_owned(bundle.id, owner.id)).id == bundle.id
        assert await config_repo.get_owned(bundle.id, other.id) is None

    async def test_get_owned_loads_all_relations(
        self, db_session, config_repo, config_bundle_with_skill_and_tool,
        sample_knowledge_pack, sample_user
    ):
        bundle = config_bundle_with_skill_and_tool
        bundle.knowledge_packs.append(sample_knowledge_pack)
        await db_session.commit()
        db_session.expunge_all()

        found = await config_repo.get_owned(bundle.id, sample_user.id)

        assert len(found.skills) == 1
        assert len(found.tools) == 1
        assert [p.id for p in found.knowledge_packs] == [sample_knowledge_pack.id]

    async def test_list_for_user_returns_only_own_bundles_newest_first(
        self, config_repo, make_user, make_agent, make_bundle
    ):
        owner = await make_user()
        other = await make_user()
        agent = await make_agent()
        first = await make_bundle(owner, agent)
        second = await make_bundle(owner, agent)
        third = await make_bundle(owner, agent)
        await make_bundle(other, agent)

        result = await config_repo.list_for_user(owner.id)

        assert [b.id for b in result] == [third.id, second.id, first.id]

    async def test_list_for_user_paginates(
        self, config_repo, make_user, make_agent, make_bundle
    ):
        owner = await make_user()
        agent = await make_agent()
        first = await make_bundle(owner, agent)
        second = await make_bundle(owner, agent)
        await make_bundle(owner, agent)

        page = await config_repo.list_for_user(owner.id, limit=2, offset=1)

        assert [b.id for b in page] == [second.id, first.id]

    async def test_get_for_user_and_agent(
        self, config_repo, make_user, make_agent, make_bundle
    ):
        owner = await make_user()
        other = await make_user()
        agent = await make_agent()
        other_agent = await make_agent()
        match_a = await make_bundle(owner, agent)
        match_b = await make_bundle(owner, agent)
        await make_bundle(owner, other_agent)
        await make_bundle(other, agent)

        result = await config_repo.get_for_user_and_agent(owner.id, agent.id)

        assert {b.id for b in result} == {match_a.id, match_b.id}
        assert await config_repo.get_for_user_and_agent(999999, 999999) == []

    async def test_get_by_user_and_name_is_scoped_to_user(
        self, config_repo, make_user, make_agent, make_bundle
    ):
        owner = await make_user()
        other = await make_user()
        agent = await make_agent()
        mine = await make_bundle(owner, agent, name="shared-name")
        theirs = await make_bundle(other, agent, name="shared-name")

        assert (await config_repo.get_by_user_and_name(owner.id, "shared-name")).id == mine.id
        assert (await config_repo.get_by_user_and_name(other.id, "shared-name")).id == theirs.id
        assert await config_repo.get_by_user_and_name(owner.id, "missing") is None

    async def test_get_unscoped_with_relations_ignores_owner(
        self, db_session, config_repo, config_bundle_with_skill_and_tool
    ):
        bundle_id = config_bundle_with_skill_and_tool.id
        db_session.expunge_all()

        found = await config_repo.get_unscoped_with_relations(bundle_id)

        assert found.id == bundle_id
        assert len(found.skills) == 1
        assert len(found.tools) == 1
        assert await config_repo.get_unscoped_with_relations(999999) is None


class TestUsersAffectedByItem:

    async def test_list_user_ids_with_skill_merges_direct_and_profile_links(
        self, db_session, config_repo, make_user, make_agent, make_bundle, make_skill
    ):
        direct_user = await make_user()
        profile_user = await make_user()
        both_user = await make_user()
        unrelated_user = await make_user()
        agent = await make_agent()
        plain_agent = await make_agent()
        skill = await make_skill()

        direct_bundle = await make_bundle(direct_user, plain_agent)
        direct_bundle.skills.append(skill)
        agent.skills.append(skill)
        await make_bundle(profile_user, agent)
        both_direct = await make_bundle(both_user, agent)
        both_direct.skills.append(skill)
        await make_bundle(both_user, plain_agent)
        await make_bundle(unrelated_user, plain_agent)
        await db_session.commit()

        result = await config_repo.list_user_ids_with_skill(skill.id)

        assert sorted(result) == sorted([direct_user.id, profile_user.id, both_user.id])
        assert len(result) == len(set(result))

    async def test_list_user_ids_with_tool_merges_direct_and_profile_links(
        self, db_session, config_repo, make_user, make_agent, make_bundle, make_tool
    ):
        direct_user = await make_user()
        profile_user = await make_user()
        unrelated_user = await make_user()
        agent = await make_agent()
        plain_agent = await make_agent()
        tool = await make_tool()

        direct_bundle = await make_bundle(direct_user, plain_agent)
        direct_bundle.tools.append(tool)
        agent.tools.append(tool)
        await make_bundle(profile_user, agent)
        await make_bundle(unrelated_user, plain_agent)
        await db_session.commit()

        result = await config_repo.list_user_ids_with_tool(tool.id)

        assert sorted(result) == sorted([direct_user.id, profile_user.id])

    async def test_returns_empty_when_nobody_uses_the_item(
        self, config_repo, make_skill, make_tool
    ):
        skill = await make_skill()
        tool = await make_tool()

        assert await config_repo.list_user_ids_with_skill(skill.id) == []
        assert await config_repo.list_user_ids_with_tool(tool.id) == []


class TestLinks:

    async def test_add_skill_appends_once(self, config_repo, sample_config_bundle, sample_skill):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await config_repo.add_skill(sample_config_bundle, sample_skill)

        assert [s.id for s in sample_config_bundle.skills] == [sample_skill.id]

    async def test_remove_skill_removes_existing(
        self, config_repo, sample_config_bundle, sample_skill
    ):
        await config_repo.add_skill(sample_config_bundle, sample_skill)

        await config_repo.remove_skill(sample_config_bundle, sample_skill)

        assert sample_skill not in sample_config_bundle.skills

    async def test_remove_skill_noop_when_absent(
        self, config_repo, sample_config_bundle, sample_skill
    ):
        result = await config_repo.remove_skill(sample_config_bundle, sample_skill)

        assert result is sample_config_bundle
        assert sample_config_bundle.skills == []

    async def test_add_tool_appends_once(self, config_repo, sample_config_bundle, sample_tool):
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await config_repo.add_tool(sample_config_bundle, sample_tool)

        assert [t.id for t in sample_config_bundle.tools] == [sample_tool.id]

    async def test_remove_tool_removes_existing(
        self, config_repo, sample_config_bundle, sample_tool
    ):
        await config_repo.add_tool(sample_config_bundle, sample_tool)

        await config_repo.remove_tool(sample_config_bundle, sample_tool)

        assert sample_tool not in sample_config_bundle.tools

    async def test_remove_tool_noop_when_absent(
        self, config_repo, sample_config_bundle, sample_tool
    ):
        result = await config_repo.remove_tool(sample_config_bundle, sample_tool)

        assert result is sample_config_bundle
        assert sample_config_bundle.tools == []

    async def test_add_knowledge_pack_appends_once(
        self, config_repo, sample_config_bundle, sample_knowledge_pack
    ):
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)

        assert [p.id for p in sample_config_bundle.knowledge_packs] == [sample_knowledge_pack.id]

    async def test_remove_knowledge_pack_removes_existing(
        self, config_repo, sample_config_bundle, sample_knowledge_pack
    ):
        await config_repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)

        await config_repo.remove_knowledge_pack(sample_config_bundle, sample_knowledge_pack)

        assert sample_knowledge_pack not in sample_config_bundle.knowledge_packs

    async def test_remove_knowledge_pack_noop_when_absent(
        self, config_repo, sample_config_bundle, sample_knowledge_pack
    ):
        result = await config_repo.remove_knowledge_pack(
            sample_config_bundle, sample_knowledge_pack
        )

        assert result is sample_config_bundle
        assert sample_config_bundle.knowledge_packs == []