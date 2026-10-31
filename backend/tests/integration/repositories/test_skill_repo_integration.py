import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.enums.skill_visibility import SkillVisibility
from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.skill_usage_events import SkillUsageEvent
from src.db.models.skills_domain import SkillDomain
from src.repositories.skill_repo import SkillRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def skill_repo(db_session):
    return SkillRepository(db_session)


async def usage_events(session, skill_id):
    result = await session.execute(
        select(SkillUsageEvent).where(SkillUsageEvent.skill_id == skill_id)
    )
    return result.scalars().all()


async def domain_links(session, skill_id, domain_id):
    result = await session.execute(
        select(SkillDomain).where(
            SkillDomain.skill_id == skill_id, SkillDomain.domain_id == domain_id
        )
    )
    return result.scalars().all()


class TestSkillUniqueConstraints:

    async def test_cannot_create_two_global_skills_with_same_name(
        self, skill_repo, db_session
    ):
        await skill_repo.create(
            skill_name="duplicate-skill", description="First",
            visibility=SkillVisibility.GLOBAL,
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await skill_repo.create(
                skill_name="duplicate-skill", description="Second",
                visibility=SkillVisibility.GLOBAL,
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_same_owner_cannot_have_two_skills_with_same_name(
        self, skill_repo, db_session, make_user, make_skill
    ):
        owner = await make_user()
        await make_skill(owner=owner, skill_name="mine")

        with pytest.raises(IntegrityError):
            await make_skill(owner=owner, skill_name="mine")

        await db_session.rollback()

    async def test_different_owners_may_share_a_skill_name(
        self, make_user, make_skill
    ):
        first = await make_skill(owner=await make_user(), skill_name="shared")
        second = await make_skill(owner=await make_user(), skill_name="shared")

        assert first.id != second.id


class TestSkillRecordSelectionSideEffects:

    async def test_record_selection_persists_one_usage_event(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        await skill_repo.record_selection(sample_skill.id, sample_user.id)
        await db_session.commit()

        events = await usage_events(db_session, sample_skill.id)

        assert len(events) == 1
        assert events[0].user_id == sample_user.id

    async def test_record_selection_freq_increment_is_persisted(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        initial = sample_skill.skill_selected_freq

        await skill_repo.record_selection(sample_skill.id, sample_user.id)
        await db_session.commit()
        db_session.expunge_all()

        reloaded = await skill_repo.admin_get_by_id(sample_skill.id)

        assert reloaded.skill_selected_freq == initial + 1

    async def test_multiple_selections_accumulate_freq_and_events(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        initial = sample_skill.skill_selected_freq

        for _ in range(3):
            await skill_repo.record_selection(sample_skill.id, sample_user.id)
        await db_session.commit()
        db_session.expunge_all()

        reloaded = await skill_repo.admin_get_by_id(sample_skill.id)

        assert reloaded.skill_selected_freq == initial + 3
        assert len(await usage_events(db_session, sample_skill.id)) == 3

    async def test_record_selection_with_config_bundle_persists_it_on_event(
        self, skill_repo, db_session, sample_skill, sample_user, sample_config_bundle
    ):
        await skill_repo.record_selection(
            sample_skill.id, sample_user.id, config_bundle_id=sample_config_bundle.id
        )
        await db_session.commit()

        events = await usage_events(db_session, sample_skill.id)

        assert [e.config_bundle_id for e in events] == [sample_config_bundle.id]


class TestSkillDeleteBehaviour:

    async def test_deleting_skill_cascades_usage_events(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        skill_id = sample_skill.id
        db_session.add(SkillUsageEvent(skill_id=skill_id, user_id=sample_user.id))
        await db_session.commit()

        await skill_repo.delete(sample_skill)
        await db_session.commit()

        assert await usage_events(db_session, skill_id) == []


class TestSkillArchive:

    async def test_archive_is_persisted_and_hides_from_visible_queries(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        skill_id = sample_skill.id

        await skill_repo.archive(sample_skill)
        await db_session.commit()
        db_session.expunge_all()

        assert await skill_repo.get_visible(skill_id, sample_user.id) is None
        assert skill_id not in {s.id for s in await skill_repo.list_visible(sample_user.id)}
        assert (await skill_repo.admin_get_by_id(skill_id)).archived_at is not None

    async def test_restore_is_persisted(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        skill_id = sample_skill.id
        await skill_repo.archive(sample_skill)
        await db_session.commit()

        await skill_repo.restore(sample_skill)
        await db_session.commit()
        db_session.expunge_all()

        assert (await skill_repo.get_visible(skill_id, sample_user.id)).id == skill_id


class TestSkillDomainAssociation:

    async def test_add_domain_is_persisted(
        self, skill_repo, db_session, sample_skill, sample_knowledge_domain
    ):
        await skill_repo.add_domain(sample_skill, sample_knowledge_domain)
        await db_session.commit()

        links = await domain_links(db_session, sample_skill.id, sample_knowledge_domain.id)

        assert len(links) == 1

    async def test_add_domain_twice_creates_one_link(
        self, skill_repo, db_session, sample_skill, sample_knowledge_domain
    ):
        await skill_repo.add_domain(sample_skill, sample_knowledge_domain)
        await skill_repo.add_domain(sample_skill, sample_knowledge_domain)
        await db_session.commit()

        links = await domain_links(db_session, sample_skill.id, sample_knowledge_domain.id)

        assert len(links) == 1

    async def test_list_visible_by_domain_reflects_persisted_association(
        self, skill_repo, db_session, sample_user, sample_skill, another_skill,
        sample_knowledge_domain
    ):
        await skill_repo.add_domain(sample_skill, sample_knowledge_domain)
        await db_session.commit()

        results = await skill_repo.list_visible(
            sample_user.id, domain_id=sample_knowledge_domain.id
        )

        assert [s.id for s in results] == [sample_skill.id]

    async def test_deleting_domain_removes_link_but_not_skill(
        self, skill_repo, db_session, sample_skill, sample_knowledge_domain
    ):
        skill_id, domain_id = sample_skill.id, sample_knowledge_domain.id
        await skill_repo.add_domain(sample_skill, sample_knowledge_domain)
        await db_session.commit()

        domain = await db_session.get(KnowledgeDomain, domain_id)
        await db_session.delete(domain)
        await db_session.commit()
        db_session.expunge_all()

        assert await domain_links(db_session, skill_id, domain_id) == []
        assert await skill_repo.admin_get_by_id(skill_id) is not None

    async def test_deleting_skill_does_not_delete_domain(
        self, skill_repo, db_session, sample_skill, sample_knowledge_domain
    ):
        domain_id = sample_knowledge_domain.id
        await skill_repo.add_domain(sample_skill, sample_knowledge_domain)
        await db_session.commit()

        await skill_repo.delete(sample_skill)
        await db_session.commit()

        result = await db_session.execute(
            select(KnowledgeDomain)
            .where(KnowledgeDomain.id == domain_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is not None