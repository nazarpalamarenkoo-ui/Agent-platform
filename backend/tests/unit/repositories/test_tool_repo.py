from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.enums.tool_auth_type import ToolAuthType
from src.db.models.tool_usage_events import ToolUsageEvent
from src.repositories.tool_repo import ToolDefinitionRepository

pytestmark = pytest.mark.db


def archived():
    return datetime.now(timezone.utc)


@pytest.fixture
def tool_repo(db_session):
    return ToolDefinitionRepository(db_session)


class TestDisabledMethods:

    async def test_get_by_id_is_disabled(self, tool_repo):
        with pytest.raises(NotImplementedError):
            await tool_repo.get_by_id(1)

    async def test_get_all_is_disabled(self, tool_repo):
        with pytest.raises(NotImplementedError):
            await tool_repo.get_all()


class TestGlobalCatalog:

    async def test_list_active_returns_only_global_not_archived(
        self, tool_repo, make_user, make_tool
    ):
        owner = await make_user()
        active = await make_tool()
        await make_tool(archived_at=archived())
        await make_tool(owner=owner)

        result = await tool_repo.list_active()

        assert {t.id for t in result} == {active.id}

    async def test_list_active_orders_by_name_and_paginates(self, tool_repo, make_tool):
        await make_tool(tool_name="b-tool")
        await make_tool(tool_name="a-tool")
        await make_tool(tool_name="c-tool")

        page = await tool_repo.list_active(limit=2, offset=1)

        assert [t.tool_name for t in page] == ["b-tool", "c-tool"]

    async def test_list_active_filters_by_domain(
        self, tool_repo, make_tool, domain_scoped_tool, another_knowledge_domain
    ):
        await make_tool()

        result = await tool_repo.list_active(domain_id=another_knowledge_domain.id)

        assert [t.id for t in result] == [domain_scoped_tool.id]

    async def test_get_active_ignores_private_and_archived(
        self, tool_repo, make_user, make_tool
    ):
        owner = await make_user()
        active = await make_tool()
        private = await make_tool(owner=owner)
        old = await make_tool(archived_at=archived())

        assert (await tool_repo.get_active(active.id)).id == active.id
        assert await tool_repo.get_active(private.id) is None
        assert await tool_repo.get_active(old.id) is None

    async def test_get_active_many_returns_global_active_only(
        self, tool_repo, make_user, make_tool
    ):
        owner = await make_user()
        active = await make_tool()
        private = await make_tool(owner=owner)
        old = await make_tool(archived_at=archived())

        result = await tool_repo.get_active_many([active.id, private.id, old.id, active.id])

        assert [t.id for t in result] == [active.id]
        assert await tool_repo.get_active_many([]) == []


class TestVisibility:

    async def test_list_visible_returns_global_and_own_private_only(
        self, tool_repo, make_user, make_tool
    ):
        viewer = await make_user()
        other = await make_user()
        global_tool = await make_tool()
        mine = await make_tool(owner=viewer)
        await make_tool(owner=other)
        await make_tool(archived_at=archived())
        await make_tool(owner=viewer, archived_at=archived())

        result = await tool_repo.list_visible(viewer.id)

        assert {t.id for t in result} == {global_tool.id, mine.id}

    async def test_list_visible_filters_by_domain(
        self, tool_repo, make_user, make_tool, domain_scoped_tool, another_knowledge_domain
    ):
        viewer = await make_user()
        await make_tool()

        result = await tool_repo.list_visible(viewer.id, domain_id=another_knowledge_domain.id)

        assert [t.id for t in result] == [domain_scoped_tool.id]

    async def test_get_visible(self, tool_repo, make_user, make_tool):
        viewer = await make_user()
        other = await make_user()
        mine = await make_tool(owner=viewer)
        theirs = await make_tool(owner=other)

        assert (await tool_repo.get_visible(mine.id, viewer.id)).id == mine.id
        assert await tool_repo.get_visible(theirs.id, viewer.id) is None

    async def test_get_visible_many(self, tool_repo, make_user, make_tool):
        viewer = await make_user()
        other = await make_user()
        global_tool = await make_tool()
        theirs = await make_tool(owner=other)

        result = await tool_repo.get_visible_many([global_tool.id, theirs.id], viewer.id)

        assert [t.id for t in result] == [global_tool.id]
        assert await tool_repo.get_visible_many([], viewer.id) == []

    async def test_get_global_active_many_excludes_private_and_archived(
        self, tool_repo, make_user, make_tool
    ):
        owner = await make_user()
        active = await make_tool()
        private = await make_tool(owner=owner)
        old = await make_tool(archived_at=archived())

        result = await tool_repo.get_global_active_many([active.id, private.id, old.id])

        assert [t.id for t in result] == [active.id]

    async def test_list_and_count_candidates(self, tool_repo, make_user, make_tool):
        viewer = await make_user()
        other = await make_user()
        first = await make_tool(description="first")
        second = await make_tool(owner=viewer, description="second")
        await make_tool(owner=other)
        await make_tool(archived_at=archived())

        rows = await tool_repo.list_candidates(viewer.id)

        assert [(r.id, r.description) for r in rows] == [
            (first.id, "first"),
            (second.id, "second"),
        ]
        assert await tool_repo.count_candidates(viewer.id) == 2


class TestAdminAndOwnerQueries:

    async def test_admin_list_global_excludes_private_and_archived_by_default(
        self, tool_repo, make_user, make_tool
    ):
        owner = await make_user()
        active = await make_tool()
        old = await make_tool(archived_at=archived())
        await make_tool(owner=owner)

        default = await tool_repo.admin_list_global()
        with_archived = await tool_repo.admin_list_global(include_archived=True)

        assert {t.id for t in default} == {active.id}
        assert {t.id for t in with_archived} == {active.id, old.id}

    async def test_admin_list_includes_private_tools(self, tool_repo, make_user, make_tool):
        owner = await make_user()
        global_tool = await make_tool()
        private = await make_tool(owner=owner)
        old = await make_tool(archived_at=archived())

        default = await tool_repo.admin_list()
        with_archived = await tool_repo.admin_list(include_archived=True)

        assert {t.id for t in default} == {global_tool.id, private.id}
        assert {t.id for t in with_archived} == {global_tool.id, private.id, old.id}

    async def test_admin_get_by_id_sees_everything(self, tool_repo, make_user, make_tool):
        owner = await make_user()
        private = await make_tool(owner=owner, archived_at=archived())

        assert (await tool_repo.admin_get_by_id(private.id)).id == private.id
        assert await tool_repo.admin_get_by_id(999999) is None

    async def test_admin_get_by_name_returns_global_only(self, tool_repo, make_user, make_tool):
        owner = await make_user()
        global_tool = await make_tool(tool_name="shared-name")
        await make_tool(owner=owner, tool_name="shared-name")

        assert (await tool_repo.admin_get_by_name("shared-name")).id == global_tool.id

    async def test_owned_lookups(self, tool_repo, make_user, make_tool):
        owner = await make_user()
        other = await make_user()
        active = await make_tool(owner=owner, tool_name="mine")
        old = await make_tool(owner=owner, archived_at=archived())
        await make_tool(owner=other, tool_name="mine")

        assert (await tool_repo.get_owned_by_id(active.id, owner.id)).id == active.id
        assert await tool_repo.get_owned_by_id(active.id, other.id) is None
        assert (await tool_repo.get_owned_by_name("mine", owner.id)).id == active.id
        assert {t.id for t in await tool_repo.list_owned(owner.id)} == {active.id}
        assert {t.id for t in await tool_repo.list_owned(owner.id, include_archived=True)} == {
            active.id,
            old.id,
        }
        assert await tool_repo.count_owned_active(owner.id) == 1


class TestEffectiveSetForBundle:

    @pytest_asyncio.fixture
    async def scene(self, db_session, make_user, make_agent, make_bundle, make_tool):
        user = await make_user()
        agent = await make_agent()
        other_agent = await make_agent()
        bundle = await make_bundle(user, agent)

        direct = await make_tool(auth_type=ToolAuthType.BEARER, tool_name="direct-tool")
        via_profile = await make_tool()
        in_both = await make_tool()
        unrelated = await make_tool()
        other_profile_only = await make_tool()

        bundle.tools.extend([direct, in_both])
        agent.tools.extend([via_profile, in_both])
        other_agent.tools.append(other_profile_only)
        await db_session.commit()

        return dict(
            bundle=bundle,
            direct=direct,
            via_profile=via_profile,
            in_both=in_both,
            unrelated=unrelated,
            other_profile_only=other_profile_only,
        )

    async def test_list_for_bundle_merges_direct_and_profile_tools_without_duplicates(
        self, tool_repo, scene
    ):
        result = await tool_repo.list_for_bundle(scene["bundle"].id)

        ids = [t.id for t in result]
        assert sorted(ids) == sorted(
            [scene["direct"].id, scene["via_profile"].id, scene["in_both"].id]
        )
        assert len(ids) == len(set(ids))

    async def test_get_for_bundle(self, tool_repo, scene):
        bundle_id = scene["bundle"].id

        assert (await tool_repo.get_for_bundle(scene["via_profile"].id, bundle_id)) is not None
        assert await tool_repo.get_for_bundle(scene["unrelated"].id, bundle_id) is None
        assert await tool_repo.get_for_bundle(scene["other_profile_only"].id, bundle_id) is None

    async def test_manifest_exposes_connection_details_and_archive_flag(
        self, db_session, tool_repo, scene
    ):
        scene["direct"].archived_at = archived()
        await db_session.commit()

        rows = await tool_repo.list_manifest_for_bundle(scene["bundle"].id)

        by_id = {r.id: r for r in rows}
        direct = by_id[scene["direct"].id]
        assert direct.tool_name == "direct-tool"
        assert direct.url == scene["direct"].url
        assert direct.auth_type == ToolAuthType.BEARER
        assert direct.owner_id is None
        assert direct.archived_at is not None
        assert by_id[scene["via_profile"].id].archived_at is None
        assert [r.id for r in rows] == sorted(by_id)


class TestArchiveAndRestore:

    async def test_archive_sets_timestamp_once(self, tool_repo, make_tool):
        tool = await make_tool()

        await tool_repo.archive(tool)
        first = tool.archived_at
        await tool_repo.archive(tool)

        assert first is not None
        assert tool.archived_at == first

    async def test_restore_clears_timestamp(self, tool_repo, make_tool):
        tool = await make_tool(archived_at=archived())

        await tool_repo.restore(tool)

        assert tool.archived_at is None


class TestRecordSelection:

    async def test_increments_counter_and_writes_event(
        self, db_session, tool_repo, make_user, make_tool
    ):
        user = await make_user()
        tool = await make_tool()

        await tool_repo.record_selection(tool.id, user.id)
        result = await tool_repo.record_selection(tool.id, user.id)

        assert result.id == tool.id
        assert tool.tool_selected_freq == 2
        events = (
            await db_session.execute(
                select(ToolUsageEvent).where(ToolUsageEvent.tool_id == tool.id)
            )
        ).scalars().all()
        assert len(events) == 2

    async def test_event_keeps_config_bundle_id(
        self, db_session, tool_repo, make_user, make_agent, make_bundle, make_tool
    ):
        user = await make_user()
        bundle = await make_bundle(user, await make_agent())
        tool = await make_tool()

        await tool_repo.record_selection(tool.id, user.id, config_bundle_id=bundle.id)

        event = (
            await db_session.execute(
                select(ToolUsageEvent).where(ToolUsageEvent.tool_id == tool.id)
            )
        ).scalar_one()
        assert event.config_bundle_id == bundle.id

    async def test_unknown_tool_fails_on_flush(self, db_session, tool_repo, make_user):
        user = await make_user()

        with pytest.raises(IntegrityError):
            await tool_repo.record_selection(999999, user.id)

        await db_session.rollback()


class TestAddDomain:

    async def test_appends_once(self, tool_repo, make_tool, sample_knowledge_domain):
        tool = await make_tool()

        await tool_repo.add_domain(tool, sample_knowledge_domain)
        await tool_repo.add_domain(tool, sample_knowledge_domain)

        assert [d.id for d in tool.domains] == [sample_knowledge_domain.id]

    async def test_allows_multiple_domains(
        self, tool_repo, make_tool, sample_knowledge_domain, another_knowledge_domain
    ):
        tool = await make_tool()

        await tool_repo.add_domain(tool, sample_knowledge_domain)
        await tool_repo.add_domain(tool, another_knowledge_domain)

        assert {d.id for d in tool.domains} == {
            sample_knowledge_domain.id,
            another_knowledge_domain.id,
        }