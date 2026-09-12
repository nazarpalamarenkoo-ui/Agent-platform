from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.knowledge_pack_service import KnowledgePackService


@pytest.fixture
def pack_repo():
    return AsyncMock()


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def service(pack_repo, domain_repo):
    return KnowledgePackService(pack_repo, domain_repo)


class TestCreatePack:
    async def test_creates_pack_when_domain_and_names_are_unique(
        self, service, pack_repo, domain_repo
    ):
        domain_repo.get_by_id.return_value = MagicMock()
        pack_repo.get_by_name_in_domain.return_value = None
        pack_repo.get_by_slug.return_value = None
        created = MagicMock()
        pack_repo.create.return_value = created

        result = await service.create_pack(
            name="Pack", domain_id=1, description="desc", slug="pack"
        )

        assert result is created
        pack_repo.create.assert_awaited_once_with(
            name="Pack", domain_id=1, description="desc", slug="pack"
        )

    async def test_raises_when_domain_missing(
        self, service, domain_repo, pack_repo
    ):
        domain_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Domain with id=1 does not exist"):
            await service.create_pack(
                name="Pack", domain_id=1, description="desc", slug="pack"
            )

        pack_repo.create.assert_not_awaited()

    async def test_raises_when_name_taken_in_domain(
        self, service, domain_repo, pack_repo
    ):
        domain_repo.get_by_id.return_value = MagicMock()
        pack_repo.get_by_name_in_domain.return_value = MagicMock()

        with pytest.raises(
            ValueError, match="Pack with name='Pack' already exists in domain 1"
        ):
            await service.create_pack(
                name="Pack", domain_id=1, description="desc", slug="pack"
            )

        pack_repo.create.assert_not_awaited()

    async def test_raises_when_slug_taken(
        self, service, domain_repo, pack_repo
    ):
        domain_repo.get_by_id.return_value = MagicMock()
        pack_repo.get_by_name_in_domain.return_value = None
        pack_repo.get_by_slug.return_value = MagicMock()

        with pytest.raises(
            ValueError, match="Pack with slug='pack' already exists"
        ):
            await service.create_pack(
                name="Pack", domain_id=1, description="desc", slug="pack"
            )

        pack_repo.create.assert_not_awaited()


class TestGetPackBySlug:
    async def test_returns_pack_when_found(self, service, pack_repo):
        pack = MagicMock()
        pack_repo.get_by_slug.return_value = pack

        result = await service.get_pack_by_slug("pack")

        assert result is pack

    async def test_raises_when_not_found(self, service, pack_repo):
        pack_repo.get_by_slug.return_value = None

        with pytest.raises(ValueError, match="Pack with slug='pack' not found"):
            await service.get_pack_by_slug("pack")


class TestGetPacksByDomain:
    async def test_delegates_to_repo(self, service, pack_repo):
        packs = [MagicMock()]
        pack_repo.list_by_domain.return_value = packs

        result = await service.get_packs_by_domain(domain_id=1)

        assert result is packs
        pack_repo.list_by_domain.assert_awaited_once_with(1)


class TestGetPackWithDocuments:
    async def test_returns_pack_when_found(self, service, pack_repo):
        pack = MagicMock()
        pack_repo.get_by_id_with_documents.return_value = pack

        result = await service.get_pack_with_documents(pack_id=1)

        assert result is pack

    async def test_raises_when_not_found(self, service, pack_repo):
        pack_repo.get_by_id_with_documents.return_value = None

        with pytest.raises(ValueError, match="Pack 1 not found"):
            await service.get_pack_with_documents(pack_id=1)