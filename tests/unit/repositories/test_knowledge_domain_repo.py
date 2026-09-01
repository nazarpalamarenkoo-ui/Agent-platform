import pytest

from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository

pytestmark = pytest.mark.db


@pytest.fixture
def domain_repo(db_session):
    return KnowledgeDomainRepository(db_session)


class TestKnowledgeDomainRepository:

    async def test_get_by_slug_found(self, domain_repo, sample_knowledge_domain):
        found = await domain_repo.get_by_slug(sample_knowledge_domain.slug)

        assert found is not None
        assert found.id == sample_knowledge_domain.id

    async def test_get_by_slug_not_found(self, domain_repo):
        found = await domain_repo.get_by_slug("nonexistent-slug")

        assert found is None

    async def test_get_root_domains_returns_roots(
        self, domain_repo, sample_knowledge_domain, another_knowledge_domain
    ):
        results = await domain_repo.get_root_domains()

        ids = {d.id for d in results}
        assert sample_knowledge_domain.id in ids
        assert another_knowledge_domain.id in ids

    async def test_get_root_domains_excludes_children(
        self, domain_repo, child_knowledge_domain
    ):
        results = await domain_repo.get_root_domains()

        ids = {d.id for d in results}
        assert child_knowledge_domain.id not in ids

    async def test_get_root_domains_loads_children_relation(
        self, domain_repo, sample_knowledge_domain, child_knowledge_domain, db_session
    ):
        # Expire cached state so the subsequent query sees the committed child row
        db_session.expire_all()

        results = await domain_repo.get_root_domains()

        parent = next(d for d in results if d.id == sample_knowledge_domain.id)
        child_ids = {c.id for c in parent.children}
        assert child_knowledge_domain.id in child_ids