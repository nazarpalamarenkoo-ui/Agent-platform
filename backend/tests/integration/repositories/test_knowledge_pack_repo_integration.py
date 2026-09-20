import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.db.models.knowledge_packs import KnowledgePack
from src.db.models.document import Document

pytestmark = pytest.mark.integration


@pytest.fixture
def pack_repo(db_session):
    return KnowledgePackRepository(db_session)


class TestKnowledgePackUniqueConstraints:

    async def test_cannot_create_two_packs_with_same_slug(
        self, pack_repo, db_session, sample_knowledge_domain
    ):
        await pack_repo.create(
            slug="duplicate-pack-slug",
            name="First Pack",
            domain_id=sample_knowledge_domain.id,
            description="Original",
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await pack_repo.create(
                slug="duplicate-pack-slug",
                name="Second Pack",
                domain_id=sample_knowledge_domain.id,
                description="Duplicate slug",
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_cannot_create_two_packs_with_same_name_in_same_domain(
        self, pack_repo, db_session, sample_knowledge_domain
    ):
        await pack_repo.create(
            slug="pack-a",
            name="Shared Name",
            domain_id=sample_knowledge_domain.id,
            description="First",
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await pack_repo.create(
                slug="pack-b",
                name="Shared Name",
                domain_id=sample_knowledge_domain.id,
                description="Second",
            )
            await db_session.commit()

        await db_session.rollback()

    async def test_same_name_allowed_in_different_domains(
        self, pack_repo, db_session, sample_knowledge_domain, another_knowledge_domain
    ):
        pack_a = await pack_repo.create(
            slug="pack-domain-a",
            name="Shared Name",
            domain_id=sample_knowledge_domain.id,
            description="In domain A",
        )
        await db_session.commit()

        pack_b = await pack_repo.create(
            slug="pack-domain-b",
            name="Shared Name",
            domain_id=another_knowledge_domain.id,
            description="In domain B",
        )
        await db_session.commit()
        await db_session.refresh(pack_b)

        assert pack_b.id is not None
        assert pack_b.id != pack_a.id


class TestKnowledgePackForeignKeyIntegrity:

    async def test_cannot_create_pack_with_nonexistent_domain(
        self, pack_repo, db_session
    ):
        with pytest.raises(IntegrityError):
            await pack_repo.create(
                slug="orphan-pack",
                name="Orphan Pack",
                domain_id=999_999,
                description="Bad FK",
            )
            await db_session.commit()

        await db_session.rollback()


class TestKnowledgePackDeleteBehaviour:

    async def test_deleting_pack_sets_document_pack_id_null(
        self, pack_repo, db_session, sample_knowledge_pack, classified_document
    ):
        doc_id = classified_document.id

        pack = await db_session.get(KnowledgePack, sample_knowledge_pack.id)
        await db_session.delete(pack)
        await db_session.commit()

        result = await db_session.execute(
            select(Document)
            .where(Document.id == doc_id)
            .execution_options(populate_existing=True)
        )
        reloaded = result.scalar_one()

        assert reloaded.knowledge_pack_id is None

    async def test_deleting_domain_cascades_to_pack(
        self, pack_repo, db_session, sample_knowledge_domain, sample_knowledge_pack
    ):
        from src.db.models.knowledge_domains import KnowledgeDomain

        pack_id = sample_knowledge_pack.id

        domain = await db_session.get(KnowledgeDomain, sample_knowledge_domain.id)
        await db_session.delete(domain)
        await db_session.commit()

        result = await db_session.execute(
            select(KnowledgePack)
            .where(KnowledgePack.id == pack_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is None


class TestKnowledgePackLookupsReflectPersistedState:

    async def test_get_by_slug_reflects_commit(
        self, pack_repo, db_session, sample_knowledge_domain
    ):
        created = await pack_repo.create(
            slug="lookup-pack",
            name="Lookup Pack",
            domain_id=sample_knowledge_domain.id,
            description="For slug lookup",
        )
        await db_session.commit()

        found = await pack_repo.get_by_slug("lookup-pack")

        assert found is not None
        assert found.id == created.id

    async def test_list_by_domain_reflects_commit(
        self, pack_repo, db_session, sample_knowledge_domain, another_knowledge_domain
    ):
        in_domain = await pack_repo.create(
            slug="in-domain-pack",
            name="In Domain",
            domain_id=sample_knowledge_domain.id,
            description="Belongs to sample domain",
        )
        other_domain_pack = await pack_repo.create(
            slug="other-domain-pack",
            name="Other Domain",
            domain_id=another_knowledge_domain.id,
            description="Belongs to another domain",
        )
        await db_session.commit()

        results = await pack_repo.list_by_domain(sample_knowledge_domain.id)
        ids = {p.id for p in results}

        assert in_domain.id in ids
        assert other_domain_pack.id not in ids