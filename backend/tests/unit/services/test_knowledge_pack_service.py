from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.knowledge_pack_service import KnowledgePackService

ADMIN = SimpleNamespace(id=1, is_admin=True)
USER = SimpleNamespace(id=2, is_admin=False)
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def pack_repo():
    repo = AsyncMock()
    repo.get_by_name_in_domain.return_value = None
    repo.get_by_slug.return_value = None
    return repo


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def service(pack_repo, domain_repo):
    return KnowledgePackService(pack_repo, domain_repo)


class TestCreatePack:
    async def test_creates_pack(self, service, pack_repo):
        created = SimpleNamespace(id=1)
        pack_repo.create.return_value = created

        result = await service.create_pack(ADMIN, name="Pack", domain_id=1, description="d", slug="pack")

        assert result is created
        pack_repo.create.assert_awaited_once_with(name="Pack", domain_id=1, description="d", slug="pack")

    async def test_requires_admin(self, service, domain_repo, pack_repo):
        with pytest.raises(ForbiddenError):
            await service.create_pack(USER, name="Pack", domain_id=1, description="d", slug="pack")

        domain_repo.get_by_id.assert_not_awaited()
        pack_repo.create.assert_not_awaited()

    async def test_raises_when_domain_missing(self, service, domain_repo, pack_repo):
        domain_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Domain with id=1 does not exist"):
            await service.create_pack(ADMIN, name="Pack", domain_id=1, description="d", slug="pack")

        pack_repo.create.assert_not_awaited()

    async def test_raises_when_name_taken_in_domain(self, service, pack_repo):
        pack_repo.get_by_name_in_domain.return_value = SimpleNamespace(id=2)

        with pytest.raises(ConflictError, match="name='Pack' already exists in domain 1"):
            await service.create_pack(ADMIN, name="Pack", domain_id=1, description="d", slug="pack")

        pack_repo.get_by_name_in_domain.assert_awaited_once_with(1, "Pack")
        pack_repo.create.assert_not_awaited()

    async def test_raises_when_slug_taken(self, service, pack_repo):
        pack_repo.get_by_slug.return_value = SimpleNamespace(id=2)

        with pytest.raises(ConflictError, match="slug='pack' already exists"):
            await service.create_pack(ADMIN, name="Pack", domain_id=1, description="d", slug="pack")

        pack_repo.create.assert_not_awaited()


class TestListPacks:
    async def test_regular_listing_uses_active(self, service, pack_repo):
        pack_repo.list_active.return_value = [SimpleNamespace(id=1)]

        result = await service.list_packs(USER, limit=5, offset=2)

        assert len(result) == 1
        pack_repo.list_active.assert_awaited_once_with(limit=5, offset=2)

    async def test_include_archived_requires_admin(self, service, pack_repo):
        with pytest.raises(ForbiddenError):
            await service.list_packs(USER, include_archived=True)

        pack_repo.get_all.assert_not_awaited()

    async def test_admin_gets_all_as_list(self, service, pack_repo):
        pack_repo.get_all.return_value = (SimpleNamespace(id=1), SimpleNamespace(id=2))

        result = await service.list_packs(ADMIN, include_archived=True)

        assert isinstance(result, list)
        assert len(result) == 2
        pack_repo.get_all.assert_awaited_once_with(limit=100, offset=0)


class TestGetPackBySlug:
    async def test_returns_active_pack(self, service, pack_repo):
        pack = SimpleNamespace(archived_at=None)
        pack_repo.get_by_slug.return_value = pack

        assert await service.get_pack_by_slug(USER, "pack") is pack

    async def test_not_found(self, service, pack_repo):
        with pytest.raises(NotFoundError, match="slug='pack' not found"):
            await service.get_pack_by_slug(USER, "pack")

    async def test_archived_pack_hidden_from_regular_user(self, service, pack_repo):
        pack_repo.get_by_slug.return_value = SimpleNamespace(archived_at=NOW)

        with pytest.raises(NotFoundError):
            await service.get_pack_by_slug(USER, "pack")

    async def test_archived_pack_visible_to_admin(self, service, pack_repo):
        pack = SimpleNamespace(archived_at=NOW)
        pack_repo.get_by_slug.return_value = pack

        assert await service.get_pack_by_slug(ADMIN, "pack") is pack


class TestGetPacksByDomain:
    async def test_lists_active_packs_of_domain(self, service, pack_repo):
        packs = [SimpleNamespace(id=1)]
        pack_repo.list_active.return_value = packs

        result = await service.get_packs_by_domain(USER, domain_id=3, limit=7, offset=1)

        assert result is packs
        pack_repo.list_active.assert_awaited_once_with(limit=7, offset=1, domain_id=3)


class TestGetPackWithDocuments:
    async def test_requires_admin(self, service, pack_repo):
        with pytest.raises(ForbiddenError):
            await service.get_pack_with_documents(USER, 1)

        pack_repo.get_by_id_with_documents.assert_not_awaited()

    async def test_returns_pack(self, service, pack_repo):
        pack = SimpleNamespace(id=1)
        pack_repo.get_by_id_with_documents.return_value = pack

        assert await service.get_pack_with_documents(ADMIN, 1) is pack

    async def test_not_found(self, service, pack_repo):
        pack_repo.get_by_id_with_documents.return_value = None

        with pytest.raises(NotFoundError, match="Pack 1 not found"):
            await service.get_pack_with_documents(ADMIN, 1)


class TestArchiveRestorePack:
    async def test_archive_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.archive_pack(USER, 1)

    async def test_archive_returns_repo_result(self, service, pack_repo):
        pack, archived = SimpleNamespace(id=1), SimpleNamespace(id=1, archived_at=NOW)
        pack_repo.get_by_id.return_value = pack
        pack_repo.archive.return_value = archived

        assert await service.archive_pack(ADMIN, 1) is archived
        pack_repo.archive.assert_awaited_once_with(pack)

    async def test_archive_not_found(self, service, pack_repo):
        pack_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Pack 1 not found"):
            await service.archive_pack(ADMIN, 1)

        pack_repo.archive.assert_not_awaited()

    async def test_restore_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.restore_pack(USER, 1)

    async def test_restore_returns_repo_result(self, service, pack_repo):
        pack, restored = SimpleNamespace(id=1), SimpleNamespace(id=1, archived_at=None)
        pack_repo.get_by_id.return_value = pack
        pack_repo.restore.return_value = restored

        assert await service.restore_pack(ADMIN, 1) is restored
        pack_repo.restore.assert_awaited_once_with(pack)

    async def test_restore_not_found(self, service, pack_repo):
        pack_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.restore_pack(ADMIN, 1)