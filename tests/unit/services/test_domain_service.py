from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.domain_service import DomainService


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def service(domain_repo):
    return DomainService(domain_repo)


class TestCreateDomain:
    async def test_creates_root_domain(self, service, domain_repo):
        domain_repo.get_by_slug.return_value = None
        created = MagicMock()
        domain_repo.create.return_value = created

        result = await service.create_domain(
            slug="backend", name="Backend", description="desc"
        )

        assert result is created
        domain_repo.get_by_id.assert_not_awaited()
        domain_repo.create.assert_awaited_once_with(
            slug="backend", name="Backend", description="desc", parent_domain_id=None
        )

    async def test_creates_child_domain_when_parent_exists(
        self, service, domain_repo
    ):
        domain_repo.get_by_id.return_value = MagicMock()
        domain_repo.get_by_slug.return_value = None
        created = MagicMock()
        domain_repo.create.return_value = created

        result = await service.create_domain(
            slug="rest", name="REST", description="desc", parent_domain_id=1
        )

        assert result is created
        domain_repo.get_by_id.assert_awaited_once_with(1)

    async def test_raises_when_parent_not_found(self, service, domain_repo):
        domain_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Parent domain 1 not found"):
            await service.create_domain(
                slug="rest", name="REST", description="desc", parent_domain_id=1
            )

        domain_repo.create.assert_not_awaited()

    async def test_raises_when_slug_already_exists(self, service, domain_repo):
        domain_repo.get_by_slug.return_value = MagicMock()

        with pytest.raises(
            ValueError, match="Domain with slug backend already exists"
        ):
            await service.create_domain(
                slug="backend", name="Backend", description="desc"
            )

        domain_repo.create.assert_not_awaited()


class TestGetDomain:
    async def test_returns_domain_when_found(self, service, domain_repo):
        domain = MagicMock()
        domain_repo.get_by_id.return_value = domain

        result = await service.get_domain(1)

        assert result is domain

    async def test_raises_when_not_found(self, service, domain_repo):
        domain_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Domain 1 not found"):
            await service.get_domain(1)


class TestGetRootDomains:
    async def test_delegates_to_repo(self, service, domain_repo):
        domains = [MagicMock()]
        domain_repo.get_root_domains.return_value = domains

        result = await service.get_root_domains()

        assert result is domains
        domain_repo.get_root_domains.assert_awaited_once()


class TestGetAllDomains:
    async def test_returns_list_with_default_pagination(
        self, service, domain_repo
    ):
        domain_repo.get_all.return_value = (MagicMock(), MagicMock())

        result = await service.get_all_domains()

        assert isinstance(result, list)
        assert len(result) == 2
        domain_repo.get_all.assert_awaited_once_with(limit=100, offset=0)

    async def test_returns_list_with_custom_pagination(
        self, service, domain_repo
    ):
        domain_repo.get_all.return_value = []

        await service.get_all_domains(limit=5, offset=15)

        domain_repo.get_all.assert_awaited_once_with(limit=5, offset=15)