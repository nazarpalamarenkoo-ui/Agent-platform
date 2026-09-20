import pytest

from src.services.domain_service import DomainService
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository


@pytest.fixture
def service(db_session):
    return DomainService(KnowledgeDomainRepository(db_session))


class TestCreateDomain:
    async def test_creates_root_domain(self, service):
        domain = await service.create_domain(
            slug="backend", name="Backend", description="desc"
        )

        fetched = await service.get_domain(domain.id)
        assert fetched.slug == "backend"
        assert fetched.parent_domain_id is None

    async def test_creates_child_domain_linked_to_real_parent(
        self, service, sample_knowledge_domain
    ):
        child = await service.create_domain(
            slug="rest-api",
            name="REST API",
            description="desc",
            parent_domain_id=sample_knowledge_domain.id,
        )

        assert child.parent_domain_id == sample_knowledge_domain.id

    async def test_raises_when_parent_does_not_exist(self, service):
        with pytest.raises(ValueError, match="Parent domain 999999 not found"):
            await service.create_domain(
                slug="orphan", name="Orphan", description="d", parent_domain_id=999_999
            )

    async def test_raises_on_duplicate_slug(self, service, sample_knowledge_domain):
        with pytest.raises(
            ValueError,
            match=f"Domain with slug {sample_knowledge_domain.slug} already exists",
        ):
            await service.create_domain(
                slug=sample_knowledge_domain.slug, name="Duplicate", description="d"
            )


class TestGetDomain:
    async def test_returns_persisted_domain(self, service, sample_knowledge_domain):
        result = await service.get_domain(sample_knowledge_domain.id)
        assert result.id == sample_knowledge_domain.id

    async def test_raises_for_unknown_id(self, service):
        with pytest.raises(ValueError, match="Domain 999999 not found"):
            await service.get_domain(999_999)


class TestGetRootDomains:
    async def test_excludes_child_domains(
        self, service, sample_knowledge_domain, child_knowledge_domain
    ):
        roots = await service.get_root_domains()

        root_ids = {d.id for d in roots}
        assert sample_knowledge_domain.id in root_ids
        assert child_knowledge_domain.id not in root_ids


class TestGetAllDomains:
    async def test_returns_all_domains_regardless_of_hierarchy(
        self, service, sample_knowledge_domain, child_knowledge_domain
    ):
        domains = await service.get_all_domains()

        ids = {d.id for d in domains}
        assert sample_knowledge_domain.id in ids
        assert child_knowledge_domain.id in ids

    async def test_respects_pagination(
        self, service, sample_knowledge_domain, another_knowledge_domain
    ):
        page = await service.get_all_domains(limit=1, offset=0)
        assert len(page) == 1