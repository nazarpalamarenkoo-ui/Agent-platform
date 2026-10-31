from datetime import datetime, timezone

import pytest

from src.repositories.agent_profile_repo import AgentProfileRepository

pytestmark = pytest.mark.db


def archived():
    return datetime.now(timezone.utc)


@pytest.fixture
def agent_repo(db_session):
    return AgentProfileRepository(db_session)


class TestDisabledMethods:

    async def test_get_by_id_is_disabled(self, agent_repo):
        with pytest.raises(NotImplementedError):
            await agent_repo.get_by_id(1)

    async def test_get_all_is_disabled(self, agent_repo):
        with pytest.raises(NotImplementedError):
            await agent_repo.get_all()


class TestActiveQueries:

    async def test_list_active_excludes_archived_and_orders_by_name(
        self, agent_repo, make_agent
    ):
        await make_agent(agent_name="b-agent")
        await make_agent(agent_name="a-agent")
        await make_agent(agent_name="old-agent", archived_at=archived())

        result = await agent_repo.list_active()

        assert [a.agent_name for a in result] == ["a-agent", "b-agent"]

    async def test_list_active_paginates(self, agent_repo, make_agent):
        for name in ("a-agent", "b-agent", "c-agent"):
            await make_agent(agent_name=name)

        page = await agent_repo.list_active(limit=1, offset=1)

        assert [a.agent_name for a in page] == ["b-agent"]

    async def test_get_active_ignores_archived(self, agent_repo, make_agent):
        active = await make_agent()
        old = await make_agent(archived_at=archived())

        assert (await agent_repo.get_active(active.id)).id == active.id
        assert await agent_repo.get_active(old.id) is None
        assert await agent_repo.get_active(999999) is None

    async def test_get_active_loads_skills_and_tools(
        self, agent_repo, agent_profile_with_skill_and_tool
    ):
        found = await agent_repo.get_active(agent_profile_with_skill_and_tool.id)

        assert len(found.skills) == 1
        assert len(found.tools) == 1

    async def test_list_candidates_returns_active_rows_ordered_by_id(
        self, agent_repo, make_agent
    ):
        first = await make_agent(description="first")
        second = await make_agent(description="second")
        await make_agent(archived_at=archived())

        rows = await agent_repo.list_candidates()

        assert [(r.id, r.description) for r in rows] == [
            (first.id, "first"),
            (second.id, "second"),
        ]

    async def test_get_neutral_returns_active_neutral_profile(self, agent_repo, make_agent):
        await make_agent()
        neutral = await make_agent(is_neutral=True)

        assert (await agent_repo.get_neutral()).id == neutral.id

    async def test_get_neutral_is_none_when_missing_or_archived(self, agent_repo, make_agent):
        assert await agent_repo.get_neutral() is None

        await make_agent(is_neutral=True, archived_at=archived())

        assert await agent_repo.get_neutral() is None


class TestAdminQueries:

    async def test_admin_get_by_id_sees_archived(self, agent_repo, make_agent):
        old = await make_agent(archived_at=archived())

        assert (await agent_repo.admin_get_by_id(old.id)).id == old.id
        assert await agent_repo.admin_get_by_id(999999) is None

    async def test_admin_list_hides_archived_unless_requested(self, agent_repo, make_agent):
        active = await make_agent()
        old = await make_agent(archived_at=archived())

        default = await agent_repo.admin_list()
        with_archived = await agent_repo.admin_list(include_archived=True)

        assert {a.id for a in default} == {active.id}
        assert {a.id for a in with_archived} == {active.id, old.id}

    async def test_admin_get_by_name_includes_archived(self, agent_repo, make_agent):
        old = await make_agent(agent_name="legacy", archived_at=archived())

        assert (await agent_repo.admin_get_by_name("legacy")).id == old.id
        assert await agent_repo.admin_get_by_name("missing") is None


class TestArchiveAndRestore:

    async def test_archive_sets_timestamp_once(self, agent_repo, make_agent):
        agent = await make_agent()

        await agent_repo.archive(agent)
        first = agent.archived_at
        await agent_repo.archive(agent)

        assert first is not None
        assert agent.archived_at == first

    async def test_restore_clears_timestamp(self, agent_repo, make_agent):
        agent = await make_agent(archived_at=archived())

        await agent_repo.restore(agent)
        assert agent.archived_at is None

        await agent_repo.restore(agent)
        assert agent.archived_at is None


class TestSkillAndToolLinks:

    async def test_add_skill_appends_once(self, agent_repo, sample_agent_profile, sample_skill):
        await agent_repo.add_skill(sample_agent_profile, sample_skill)
        await agent_repo.add_skill(sample_agent_profile, sample_skill)

        assert [s.id for s in sample_agent_profile.skills] == [sample_skill.id]

    async def test_remove_skill_removes_existing(
        self, agent_repo, sample_agent_profile, sample_skill
    ):
        await agent_repo.add_skill(sample_agent_profile, sample_skill)

        await agent_repo.remove_skill(sample_agent_profile, sample_skill)

        assert sample_skill not in sample_agent_profile.skills

    async def test_remove_skill_noop_when_absent(
        self, agent_repo, sample_agent_profile, sample_skill
    ):
        result = await agent_repo.remove_skill(sample_agent_profile, sample_skill)

        assert result is sample_agent_profile
        assert sample_agent_profile.skills == []

    async def test_add_tool_appends_once(self, agent_repo, sample_agent_profile, sample_tool):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)
        await agent_repo.add_tool(sample_agent_profile, sample_tool)

        assert [t.id for t in sample_agent_profile.tools] == [sample_tool.id]

    async def test_remove_tool_removes_existing(
        self, agent_repo, sample_agent_profile, sample_tool
    ):
        await agent_repo.add_tool(sample_agent_profile, sample_tool)

        await agent_repo.remove_tool(sample_agent_profile, sample_tool)

        assert sample_tool not in sample_agent_profile.tools

    async def test_remove_tool_noop_when_absent(
        self, agent_repo, sample_agent_profile, sample_tool
    ):
        result = await agent_repo.remove_tool(sample_agent_profile, sample_tool)

        assert result is sample_agent_profile
        assert sample_agent_profile.tools == []