import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.tool_domain import ToolDomain
from src.db.models.tool_usage_events import ToolUsageEvent
from src.repositories.tool_repo import ToolDefinitionRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def tool_repo(db_session):
    return ToolDefinitionRepository(db_session)


async def usage_events(session, tool_id):
    result = await session.execute(
        select(ToolUsageEvent).where(ToolUsageEvent.tool_id == tool_id)
    )
    return result.scalars().all()


async def domain_links(session, tool_id, domain_id):
    result = await session.execute(
        select(ToolDomain).where(
            ToolDomain.tool_id == tool_id, ToolDomain.domain_id == domain_id
        )
    )
    return result.scalars().all()


class TestToolUniqueConstraints:

    async def test_cannot_create_two_global_tools_with_same_name(
        self, tool_repo, db_session
    ):
        await tool_repo.create(
            tool_name="duplicate-tool", description="First", url="https://example.com/a"
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await tool_repo.create(
                tool_name="duplicate-tool", description="Second", url="https://example.com/b"
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_same_owner_cannot_have_two_tools_with_same_name(
        self, db_session, make_user, make_tool
    ):
        owner = await make_user()
        await make_tool(owner=owner, tool_name="mine")

        with pytest.raises(IntegrityError):
            await make_tool(owner=owner, tool_name="mine")

        await db_session.rollback()

    async def test_different_owners_may_share_a_tool_name(self, make_user, make_tool):
        first = await make_tool(owner=await make_user(), tool_name="shared")
        second = await make_tool(owner=await make_user(), tool_name="shared")

        assert first.id != second.id


class TestToolRecordSelectionSideEffects:

    async def test_record_selection_persists_one_usage_event(
        self, tool_repo, db_session, sample_tool, sample_user
    ):
        await tool_repo.record_selection(sample_tool.id, sample_user.id)
        await db_session.commit()

        events = await usage_events(db_session, sample_tool.id)

        assert len(events) == 1
        assert events[0].user_id == sample_user.id

    async def test_record_selection_freq_increment_is_persisted(
        self, tool_repo, db_session, sample_tool, sample_user
    ):
        initial = sample_tool.tool_selected_freq

        await tool_repo.record_selection(sample_tool.id, sample_user.id)
        await db_session.commit()
        db_session.expunge_all()

        reloaded = await tool_repo.admin_get_by_id(sample_tool.id)

        assert reloaded.tool_selected_freq == initial + 1

    async def test_multiple_selections_accumulate_freq_and_events(
        self, tool_repo, db_session, sample_tool, sample_user
    ):
        initial = sample_tool.tool_selected_freq

        for _ in range(3):
            await tool_repo.record_selection(sample_tool.id, sample_user.id)
        await db_session.commit()
        db_session.expunge_all()

        reloaded = await tool_repo.admin_get_by_id(sample_tool.id)

        assert reloaded.tool_selected_freq == initial + 3
        assert len(await usage_events(db_session, sample_tool.id)) == 3

    async def test_record_selection_with_config_bundle_persists_it_on_event(
        self, tool_repo, db_session, sample_tool, sample_user, sample_config_bundle
    ):
        await tool_repo.record_selection(
            sample_tool.id, sample_user.id, config_bundle_id=sample_config_bundle.id
        )
        await db_session.commit()

        events = await usage_events(db_session, sample_tool.id)

        assert [e.config_bundle_id for e in events] == [sample_config_bundle.id]


class TestToolDeleteBehaviour:

    async def test_deleting_tool_cascades_usage_events(
        self, tool_repo, db_session, sample_tool, sample_user
    ):
        tool_id = sample_tool.id
        db_session.add(ToolUsageEvent(tool_id=tool_id, user_id=sample_user.id))
        await db_session.commit()

        await tool_repo.delete(sample_tool)
        await db_session.commit()

        assert await usage_events(db_session, tool_id) == []


class TestToolArchive:

    async def test_archive_is_persisted_and_hides_from_active_and_visible_queries(
        self, tool_repo, db_session, sample_tool, sample_user
    ):
        tool_id = sample_tool.id

        await tool_repo.archive(sample_tool)
        await db_session.commit()
        db_session.expunge_all()

        assert await tool_repo.get_active(tool_id) is None
        assert await tool_repo.get_visible(tool_id, sample_user.id) is None
        assert tool_id not in {t.id for t in await tool_repo.list_active()}
        assert (await tool_repo.admin_get_by_id(tool_id)).archived_at is not None

    async def test_restore_is_persisted(self, tool_repo, db_session, sample_tool):
        tool_id = sample_tool.id
        await tool_repo.archive(sample_tool)
        await db_session.commit()

        await tool_repo.restore(sample_tool)
        await db_session.commit()
        db_session.expunge_all()

        assert (await tool_repo.get_active(tool_id)).id == tool_id


class TestToolDomainAssociation:

    async def test_add_domain_is_persisted_once(
        self, tool_repo, db_session, sample_tool, sample_knowledge_domain
    ):
        await tool_repo.add_domain(sample_tool, sample_knowledge_domain)
        await tool_repo.add_domain(sample_tool, sample_knowledge_domain)
        await db_session.commit()

        links = await domain_links(db_session, sample_tool.id, sample_knowledge_domain.id)

        assert len(links) == 1

    async def test_list_visible_by_domain_reflects_persisted_association(
        self, tool_repo, db_session, sample_user, sample_tool, another_tool,
        sample_knowledge_domain
    ):
        await tool_repo.add_domain(sample_tool, sample_knowledge_domain)
        await db_session.commit()

        results = await tool_repo.list_visible(
            sample_user.id, domain_id=sample_knowledge_domain.id
        )

        assert [t.id for t in results] == [sample_tool.id]

    async def test_deleting_domain_removes_link_but_not_tool(
        self, tool_repo, db_session, sample_tool, sample_knowledge_domain
    ):
        tool_id, domain_id = sample_tool.id, sample_knowledge_domain.id
        await tool_repo.add_domain(sample_tool, sample_knowledge_domain)
        await db_session.commit()

        domain = await db_session.get(KnowledgeDomain, domain_id)
        await db_session.delete(domain)
        await db_session.commit()
        db_session.expunge_all()

        assert await domain_links(db_session, tool_id, domain_id) == []
        assert await tool_repo.admin_get_by_id(tool_id) is not None