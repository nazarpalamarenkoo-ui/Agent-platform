import pytest

from src.repositories.knowledge_pack_repo import KnowledgePackRepository

pytestmark = pytest.mark.db


@pytest.fixture
def pack_repo(db_session):
    return KnowledgePackRepository(db_session)


class TestKnowledgePackRepository:

    async def test_get_by_slug_found(self, pack_repo, sample_knowledge_pack):
        found = await pack_repo.get_by_slug(sample_knowledge_pack.slug)

        assert found is not None
        assert found.id == sample_knowledge_pack.id

    async def test_get_by_slug_not_found(self, pack_repo):
        found = await pack_repo.get_by_slug("nonexistent-slug")

        assert found is None

    async def test_get_by_slugs_returns_matching(
        self, pack_repo, sample_knowledge_pack, another_knowledge_pack
    ):
        results = await pack_repo.get_by_slugs(
            [sample_knowledge_pack.slug, another_knowledge_pack.slug]
        )

        ids = {p.id for p in results}
        assert sample_knowledge_pack.id in ids
        assert another_knowledge_pack.id in ids

    async def test_get_by_slugs_empty_for_unknown(self, pack_repo):
        results = await pack_repo.get_by_slugs(["nope-1", "nope-2"])

        assert results == []

    async def test_get_by_slugs_excludes_unrequested(
        self, pack_repo, sample_knowledge_pack, another_knowledge_pack
    ):
        results = await pack_repo.get_by_slugs([sample_knowledge_pack.slug])

        ids = {p.id for p in results}
        assert sample_knowledge_pack.id in ids
        assert another_knowledge_pack.id not in ids

    async def test_get_by_name_in_domain_found(
        self, pack_repo, sample_knowledge_pack, sample_knowledge_domain
    ):
        found = await pack_repo.get_by_name_in_domain(
            sample_knowledge_domain.id, sample_knowledge_pack.name
        )

        assert found is not None
        assert found.id == sample_knowledge_pack.id

    async def test_get_by_name_in_domain_wrong_domain(
        self, pack_repo, sample_knowledge_pack, another_knowledge_domain
    ):
        found = await pack_repo.get_by_name_in_domain(
            another_knowledge_domain.id, sample_knowledge_pack.name
        )

        assert found is None

    async def test_get_by_name_in_domain_wrong_name(
        self, pack_repo, sample_knowledge_domain
    ):
        found = await pack_repo.get_by_name_in_domain(
            sample_knowledge_domain.id, "nonexistent-pack-name"
        )

        assert found is None

    async def test_list_by_domain_returns_packs(
        self, pack_repo, sample_knowledge_pack, sample_knowledge_domain
    ):
        results = await pack_repo.list_by_domain(sample_knowledge_domain.id)

        ids = {p.id for p in results}
        assert sample_knowledge_pack.id in ids

    async def test_list_by_domain_empty_for_unknown(self, pack_repo):
        results = await pack_repo.list_by_domain(999999)

        assert results == []

    async def test_list_by_domain_excludes_other_domains(
        self, pack_repo, sample_knowledge_pack, another_knowledge_domain
    ):
        results = await pack_repo.list_by_domain(another_knowledge_domain.id)

        ids = {p.id for p in results}
        assert sample_knowledge_pack.id not in ids

    async def test_get_by_id_with_documents_found(
        self, pack_repo, sample_knowledge_pack, classified_document, db_session
    ):
        await db_session.refresh(sample_knowledge_pack, attribute_names=["documents"])

        found = await pack_repo.get_by_id_with_documents(sample_knowledge_pack.id)

        assert found is not None
        assert classified_document.id in {d.id for d in found.documents}

    async def test_get_by_id_with_documents_not_found(self, pack_repo):
        found = await pack_repo.get_by_id_with_documents(999999)

        assert found is None

    async def test_get_by_id_with_documents_empty_list_when_no_docs(
        self, pack_repo, another_knowledge_pack
    ):
        found = await pack_repo.get_by_id_with_documents(another_knowledge_pack.id)

        assert found is not None
        assert found.documents == []