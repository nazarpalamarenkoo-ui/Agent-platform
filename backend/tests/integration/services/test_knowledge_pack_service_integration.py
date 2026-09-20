import pytest

from src.services.knowledge_pack_service import KnowledgePackService
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository


@pytest.fixture
def service(db_session):
    return KnowledgePackService(
        KnowledgePackRepository(db_session), KnowledgeDomainRepository(db_session)
    )


class TestCreatePack:
    async def test_creates_pack_under_real_domain(
        self, service, sample_knowledge_domain
    ):
        pack = await service.create_pack(
            name="New Pack",
            domain_id=sample_knowledge_domain.id,
            description="desc",
            slug="new-pack",
        )

        fetched = await service.get_pack_by_slug("new-pack")
        assert fetched.id == pack.id
        assert fetched.domain_id == sample_knowledge_domain.id

    async def test_raises_when_domain_missing(self, service):
        with pytest.raises(ValueError, match="Domain with id=999999 does not exist"):
            await service.create_pack(
                name="Pack", domain_id=999_999, description="desc", slug="pack"
            )

    async def test_raises_when_name_already_used_in_same_domain(
        self, service, sample_knowledge_pack, sample_knowledge_domain
    ):
        with pytest.raises(
            ValueError,
            match=(
                f"Pack with name='{sample_knowledge_pack.name}' already exists "
                f"in domain {sample_knowledge_domain.id}"
            ),
        ):
            await service.create_pack(
                name=sample_knowledge_pack.name,
                domain_id=sample_knowledge_domain.id,
                description="desc",
                slug="a-different-slug",
            )

    async def test_allows_same_name_in_a_different_domain(
        self, service, sample_knowledge_pack, another_knowledge_domain
    ):
        pack = await service.create_pack(
            name=sample_knowledge_pack.name,
            domain_id=another_knowledge_domain.id,
            description="desc",
            slug="same-name-other-domain",
        )

        assert pack.name == sample_knowledge_pack.name
        assert pack.domain_id == another_knowledge_domain.id

    async def test_raises_when_slug_already_used(
        self, service, sample_knowledge_pack, another_knowledge_domain
    ):
        with pytest.raises(
            ValueError,
            match=f"Pack with slug='{sample_knowledge_pack.slug}' already exists",
        ):
            await service.create_pack(
                name="A totally different name",
                domain_id=another_knowledge_domain.id,
                description="desc",
                slug=sample_knowledge_pack.slug,
            )


class TestGetPackBySlug:
    async def test_returns_persisted_pack(self, service, sample_knowledge_pack):
        result = await service.get_pack_by_slug(sample_knowledge_pack.slug)
        assert result.id == sample_knowledge_pack.id

    async def test_raises_for_unknown_slug(self, service):
        with pytest.raises(ValueError, match="Pack with slug='missing' not found"):
            await service.get_pack_by_slug("missing")


class TestGetPacksByDomain:
    async def test_only_returns_packs_for_that_domain(
        self, service, sample_knowledge_pack, another_knowledge_pack, sample_knowledge_domain
    ):
        result = await service.get_packs_by_domain(sample_knowledge_domain.id)

        ids = {p.id for p in result}
        assert sample_knowledge_pack.id in ids
        assert another_knowledge_pack.id not in ids


class TestGetPackWithDocuments:
    async def test_includes_related_documents(
        self, service, sample_knowledge_pack, classified_document
    ):
        result = await service.get_pack_with_documents(sample_knowledge_pack.id)

        doc_ids = {d.id for d in result.documents}
        assert classified_document.id in doc_ids

    async def test_raises_for_unknown_pack(self, service):
        with pytest.raises(ValueError, match="Pack 999999 not found"):
            await service.get_pack_with_documents(999_999)