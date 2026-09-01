import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.repositories.skill_repo import SkillRepository
from src.db.models.skill_usage_events import SkillUsageEvent

pytestmark = pytest.mark.integration


@pytest.fixture
def skill_repo(db_session):
    return SkillRepository(db_session)


class TestSkillUniqueConstraints:

    async def test_cannot_create_two_skills_with_same_name_in_same_domain(
        self, skill_repo, db_session, sample_knowledge_domain
    ):
        await skill_repo.create(
            skill_name="duplicate-skill",
            description="First",
            domain_id=sample_knowledge_domain.id,
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await skill_repo.create(
                skill_name="duplicate-skill",
                description="Second",
                domain_id=sample_knowledge_domain.id,
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_same_skill_name_allowed_in_different_domains(
        self, skill_repo, db_session, sample_knowledge_domain, another_knowledge_domain
    ):
        skill_a = await skill_repo.create(
            skill_name="shared-skill",
            description="In domain A",
            domain_id=sample_knowledge_domain.id,
        )
        await db_session.commit()

        skill_b = await skill_repo.create(
            skill_name="shared-skill",
            description="In domain B",
            domain_id=another_knowledge_domain.id,
        )
        await db_session.commit()
        await db_session.refresh(skill_b)

        assert skill_b.id is not None
        assert skill_b.id != skill_a.id


class TestSkillForeignKeyIntegrity:

    async def test_cannot_create_skill_with_nonexistent_domain(
        self, skill_repo, db_session
    ):
        with pytest.raises(IntegrityError):
            await skill_repo.create(
                skill_name="orphan-skill",
                description="Bad FK",
                domain_id=999_999,
            )
            await db_session.commit()

        await db_session.rollback()


class TestSkillRecordSelectionSideEffects:

    async def test_record_selection_persists_usage_event(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        await skill_repo.record_selection(sample_skill.id, sample_user.id)
        await db_session.commit()

        result = await db_session.execute(
            select(SkillUsageEvent)
            .where(SkillUsageEvent.skill_id == sample_skill.id)
            .where(SkillUsageEvent.user_id == sample_user.id)
        )
        events = result.scalars().all()

        assert len(events) >= 1

    async def test_record_selection_freq_increment_is_persisted(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        initial_freq = sample_skill.skill_selected_freq

        await skill_repo.record_selection(sample_skill.id, sample_user.id)
        await db_session.commit()

        skill_id = sample_skill.id
        db_session.expire(sample_skill)
        reloaded = await skill_repo.get_by_id(skill_id)

        assert reloaded.skill_selected_freq == initial_freq + 1

    async def test_multiple_selections_accumulate_freq(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        initial_freq = sample_skill.skill_selected_freq

        for _ in range(3):
            await skill_repo.record_selection(sample_skill.id, sample_user.id)
        await db_session.commit()

        skill_id = sample_skill.id
        db_session.expire(sample_skill)
        reloaded = await skill_repo.get_by_id(skill_id)

        assert reloaded.skill_selected_freq == initial_freq + 3


class TestSkillDeleteBehaviour:

    async def test_deleting_skill_cascades_usage_events(
        self, skill_repo, db_session, sample_skill, sample_user
    ):
        event = SkillUsageEvent(
            skill_id=sample_skill.id,
            user_id=sample_user.id,
        )
        db_session.add(event)
        await db_session.commit()
        event_id = event.id

        await skill_repo.delete(sample_skill)
        await db_session.commit()

        result = await db_session.execute(
            select(SkillUsageEvent)
            .where(SkillUsageEvent.id == event_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is None

    async def test_deleting_skill_does_not_delete_domain(
        self, skill_repo, db_session, sample_skill, sample_knowledge_domain
    ):
        from src.db.models.knowledge_domains import KnowledgeDomain

        await skill_repo.delete(sample_skill)
        await db_session.commit()

        result = await db_session.execute(
            select(KnowledgeDomain)
            .where(KnowledgeDomain.id == sample_knowledge_domain.id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is not None


class TestSkillChangeDomain:

    async def test_change_domain_is_persisted(
        self, skill_repo, db_session, sample_skill, another_knowledge_domain
    ):
        await skill_repo.change_domain(sample_skill, another_knowledge_domain)
        await db_session.commit()

        skill_id = sample_skill.id
        db_session.expire(sample_skill)
        reloaded = await skill_repo.get_by_id(skill_id)

        assert reloaded.domain_id == another_knowledge_domain.id