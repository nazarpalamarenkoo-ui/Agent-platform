import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.db.models.knowledge_domains import KnowledgeDomain

pytestmark = pytest.mark.integration


@pytest.fixture
def domain_repo(db_session):
    return KnowledgeDomainRepository(db_session)


class TestKnowledgeDomainUniqueConstraints:

    async def test_cannot_create_two_domains_with_same_slug(
        self, domain_repo, db_session
    ):
        await domain_repo.create(
            slug="duplicate-slug",
            name="First Domain",
            description="Original",
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await domain_repo.create(
                slug="duplicate-slug",
                name="Second Domain",
                description="Duplicate",
            )
            await db_session.commit()

        await db_session.rollback()


class TestKnowledgeDomainForeignKeyIntegrity:

    async def test_cannot_create_child_with_nonexistent_parent(
        self, domain_repo, db_session
    ):
        with pytest.raises(IntegrityError):
            await domain_repo.create(
                slug="orphan-child",
                name="Orphan Child",
                description="References nonexistent parent",
                parent_domain_id=999_999,
            )
            await db_session.commit()

        await db_session.rollback()


class TestKnowledgeDomainDeleteBehaviour:

    async def test_deleting_parent_cascades_to_children(
        self, domain_repo, db_session, sample_knowledge_domain, child_knowledge_domain
    ):
        child_id = child_knowledge_domain.id

        parent = await db_session.get(KnowledgeDomain, sample_knowledge_domain.id)
        await db_session.delete(parent)
        await db_session.commit()

        result = await db_session.execute(
            select(KnowledgeDomain)
            .where(KnowledgeDomain.id == child_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is None

    async def test_deleting_domain_cascades_to_skills(
        self, domain_repo, db_session, sample_knowledge_domain, sample_skill
    ):
        from src.db.models.skills import Skill

        skill_id = sample_skill.id
        domain = await db_session.get(KnowledgeDomain, sample_knowledge_domain.id)
        await db_session.delete(domain)
        await db_session.commit()

        result = await db_session.execute(
            select(Skill)
            .where(Skill.id == skill_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is None

    async def test_deleting_child_does_not_delete_parent(
        self, domain_repo, db_session, sample_knowledge_domain, child_knowledge_domain
    ):
        parent_id = sample_knowledge_domain.id

        child = await db_session.get(KnowledgeDomain, child_knowledge_domain.id)
        await db_session.delete(child)
        await db_session.commit()

        result = await db_session.execute(
            select(KnowledgeDomain)
            .where(KnowledgeDomain.id == parent_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is not None


class TestKnowledgeDomainHierarchy:

    async def test_child_domain_references_correct_parent(
        self, domain_repo, db_session, sample_knowledge_domain, child_knowledge_domain
    ):
        child_id = child_knowledge_domain.id
        db_session.expire(child_knowledge_domain)
        reloaded = await domain_repo.get_by_id(child_id)

        assert reloaded.parent_domain_id == sample_knowledge_domain.id

    async def test_root_domain_has_no_parent(
        self, domain_repo, db_session, sample_knowledge_domain
    ):
        domain_id = sample_knowledge_domain.id
        db_session.expire(sample_knowledge_domain)
        reloaded = await domain_repo.get_by_id(domain_id)

        assert reloaded.parent_domain_id is None

    async def test_multiple_children_under_same_parent(
        self, domain_repo, db_session, sample_knowledge_domain
    ):
        child_a = await domain_repo.create(
            slug="child-a",
            name="Child A",
            description="First child",
            parent_domain_id=sample_knowledge_domain.id,
        )
        child_b = await domain_repo.create(
            slug="child-b",
            name="Child B",
            description="Second child",
            parent_domain_id=sample_knowledge_domain.id,
        )
        await db_session.commit()

        db_session.expire_all()
        roots = await domain_repo.get_root_domains()
        parent = next(d for d in roots if d.id == sample_knowledge_domain.id)

        child_ids = {c.id for c in parent.children}
        assert child_a.id in child_ids
        assert child_b.id in child_ids