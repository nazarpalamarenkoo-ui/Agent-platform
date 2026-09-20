import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.knowledge_packs import KnowledgePack
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition

pytestmark = pytest.mark.integration


class TestKnowledgeDomainSelfReferentialCascade:

    async def test_deleting_parent_domain_cascades_to_children(
        self, db_session, sample_knowledge_domain, child_knowledge_domain
    ):
        child_id = child_knowledge_domain.id

        parent_to_delete = await db_session.get(KnowledgeDomain, sample_knowledge_domain.id)
        await db_session.delete(parent_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(KnowledgeDomain).where(KnowledgeDomain.id == child_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_deleting_child_domain_does_not_affect_parent(
        self, db_session, sample_knowledge_domain, child_knowledge_domain
    ):
        parent_id = sample_knowledge_domain.id

        child_to_delete = await db_session.get(KnowledgeDomain, child_knowledge_domain.id)
        await db_session.delete(child_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(KnowledgeDomain).where(KnowledgeDomain.id == parent_id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_cannot_create_domain_with_nonexistent_parent(self, db_session):
        orphan = KnowledgeDomain(
            slug="orphan-domain",
            name="Orphan Domain",
            description="References a parent that does not exist",
            parent_domain_id=999_999,
        )
        db_session.add(orphan)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_duplicate_slug_raises_integrity_error(
        self, db_session, sample_knowledge_domain
    ):
        duplicate = KnowledgeDomain(
            slug=sample_knowledge_domain.slug,
            name="Duplicate slug domain",
            description="Should fail",
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()


class TestKnowledgeDomainSkillAndToolAssociations:

    async def test_deleting_domain_removes_skill_association_but_keeps_skill(
        self, db_session, skill_with_domain, sample_knowledge_domain
    ):
        skill_id = skill_with_domain.id

        domain_to_delete = await db_session.get(KnowledgeDomain, sample_knowledge_domain.id)
        await db_session.delete(domain_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(Skill)
            .where(Skill.id == skill_id)
            .execution_options(populate_existing=True)
        )
        reloaded_skill = result.scalar_one()
        assert reloaded_skill.domains == []

    async def test_deleting_domain_removes_tool_association_but_keeps_tool(
        self, db_session, domain_scoped_tool, another_knowledge_domain
    ):
        tool_id = domain_scoped_tool.id

        domain_to_delete = await db_session.get(KnowledgeDomain, another_knowledge_domain.id)
        await db_session.delete(domain_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(ToolDefinition)
            .where(ToolDefinition.id == tool_id)
            .execution_options(populate_existing=True)
        )
        reloaded_tool = result.scalar_one()
        assert reloaded_tool.domains == []


class TestKnowledgePackConstraints:

    async def test_duplicate_name_within_same_domain_raises_integrity_error(
        self, db_session, sample_knowledge_pack, sample_knowledge_domain
    ):
        duplicate = KnowledgePack(
            slug="a-different-slug",
            name=sample_knowledge_pack.name,
            domain_id=sample_knowledge_domain.id,
            description="Should collide on (domain_id, name)",
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_same_name_in_different_domain_is_allowed(
        self, db_session, sample_knowledge_pack, another_knowledge_domain
    ):
        pack = KnowledgePack(
            slug="another-slug-same-name",
            name=sample_knowledge_pack.name,
            domain_id=another_knowledge_domain.id,
            description="Same name, different domain",
        )
        db_session.add(pack)
        await db_session.commit()
        await db_session.refresh(pack)

        assert pack.id is not None

    async def test_duplicate_slug_raises_integrity_error(
        self, db_session, sample_knowledge_pack, another_knowledge_domain
    ):
        duplicate = KnowledgePack(
            slug=sample_knowledge_pack.slug,
            name="A different name",
            domain_id=another_knowledge_domain.id,
            description="Should collide on slug",
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_cannot_create_pack_with_nonexistent_domain_id(self, db_session):
        pack = KnowledgePack(
            slug="orphan-pack",
            name="Orphan Pack",
            domain_id=999_999,
            description="References a domain that does not exist",
        )
        db_session.add(pack)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_deleting_domain_cascades_to_knowledge_packs(
        self, db_session, sample_knowledge_pack, sample_knowledge_domain
    ):
        pack_id = sample_knowledge_pack.id

        domain_to_delete = await db_session.get(KnowledgeDomain, sample_knowledge_domain.id)
        await db_session.delete(domain_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(KnowledgePack).where(KnowledgePack.id == pack_id)
        )
        assert result.scalar_one_or_none() is None