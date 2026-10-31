import pytest
import pytest_asyncio

from src.db.enums.user_role import UserRole
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.knowledge_pack_service import KnowledgePackService


@pytest.fixture
def service(db_session):
    return KnowledgePackService(
        KnowledgePackRepository(db_session), KnowledgeDomainRepository(db_session)
    )


@pytest_asyncio.fixture
async def admin(make_user):
    return await make_user(role=UserRole.ADMIN)


class TestCreatePack:
    async def test_creates_pack_under_real_domain(
        self, service, admin, sample_knowledge_domain
    ):
        pack = await service.create_pack(
            admin, "New Pack", sample_knowledge_domain.id, "desc", "new-pack"
        )

        fetched = await service.get_pack_by_slug(admin, "new-pack")
        assert fetched.id == pack.id
        assert fetched.domain_id == sample_knowledge_domain.id

    async def test_forbidden_for_regular_user(
        self, service, sample_user, sample_knowledge_domain
    ):
        with pytest.raises(ForbiddenError, match="Admin access required"):
            await service.create_pack(
                sample_user, "P", sample_knowledge_domain.id, "d", "p"
            )

    async def test_raises_when_domain_missing(self, service, admin):
        with pytest.raises(NotFoundError, match="Domain with id=999999 does not exist"):
            await service.create_pack(admin, "Pack", 999_999, "desc", "pack")

    async def test_raises_when_name_used_in_same_domain(
        self, service, admin, sample_knowledge_pack, sample_knowledge_domain
    ):
        with pytest.raises(
            ConflictError,
            match=(
                f"Pack with name='{sample_knowledge_pack.name}' already exists "
                f"in domain {sample_knowledge_domain.id}"
            ),
        ):
            await service.create_pack(
                admin, sample_knowledge_pack.name, sample_knowledge_domain.id, "d", "other-slug"
            )

    async def test_allows_same_name_in_different_domain(
        self, service, admin, sample_knowledge_pack, another_knowledge_domain
    ):
        pack = await service.create_pack(
            admin, sample_knowledge_pack.name, another_knowledge_domain.id, "d", "same-name"
        )

        assert pack.domain_id == another_knowledge_domain.id

    async def test_raises_when_slug_used(
        self, service, admin, sample_knowledge_pack, another_knowledge_domain
    ):
        with pytest.raises(
            ConflictError,
            match=f"Pack with slug='{sample_knowledge_pack.slug}' already exists",
        ):
            await service.create_pack(
                admin, "Different", another_knowledge_domain.id, "d", sample_knowledge_pack.slug
            )


class TestGetPackBySlug:
    async def test_returns_pack(self, service, sample_user, sample_knowledge_pack):
        result = await service.get_pack_by_slug(sample_user, sample_knowledge_pack.slug)
        assert result.id == sample_knowledge_pack.id

    async def test_raises_for_unknown_slug(self, service, sample_user):
        with pytest.raises(NotFoundError, match="Pack with slug='missing' not found"):
            await service.get_pack_by_slug(sample_user, "missing")

    async def test_archived_pack_hidden_from_regular_user_but_visible_to_admin(
        self, service, admin, sample_user, sample_knowledge_pack
    ):
        await service.archive_pack(admin, sample_knowledge_pack.id)

        with pytest.raises(NotFoundError):
            await service.get_pack_by_slug(sample_user, sample_knowledge_pack.slug)
        result = await service.get_pack_by_slug(admin, sample_knowledge_pack.slug)
        assert result.id == sample_knowledge_pack.id


class TestListPacks:
    async def test_lists_active_packs(
        self, service, sample_user, sample_knowledge_pack, another_knowledge_pack
    ):
        ids = {p.id for p in await service.list_packs(sample_user)}
        assert {sample_knowledge_pack.id, another_knowledge_pack.id} <= ids

    async def test_archived_excluded_by_default(
        self, service, admin, sample_knowledge_pack
    ):
        await service.archive_pack(admin, sample_knowledge_pack.id)

        ids = {p.id for p in await service.list_packs(admin)}

        assert sample_knowledge_pack.id not in ids

    async def test_admin_can_include_archived(
        self, service, admin, sample_knowledge_pack
    ):
        await service.archive_pack(admin, sample_knowledge_pack.id)

        ids = {p.id for p in await service.list_packs(admin, include_archived=True)}

        assert sample_knowledge_pack.id in ids

    async def test_include_archived_requires_admin(self, service, sample_user):
        with pytest.raises(ForbiddenError):
            await service.list_packs(sample_user, include_archived=True)

    async def test_respects_limit_and_offset(
        self, service, sample_user, sample_knowledge_pack, another_knowledge_pack
    ):
        first = await service.list_packs(sample_user, limit=1, offset=0)
        second = await service.list_packs(sample_user, limit=1, offset=1)

        assert len(first) == len(second) == 1
        assert first[0].id != second[0].id


class TestGetPacksByDomain:
    async def test_only_returns_packs_of_that_domain(
        self, service, sample_user, sample_knowledge_pack, another_knowledge_pack,
        sample_knowledge_domain,
    ):
        ids = {
            p.id
            for p in await service.get_packs_by_domain(sample_user, sample_knowledge_domain.id)
        }

        assert sample_knowledge_pack.id in ids
        assert another_knowledge_pack.id not in ids

    async def test_excludes_archived(
        self, service, admin, sample_knowledge_pack, sample_knowledge_domain
    ):
        await service.archive_pack(admin, sample_knowledge_pack.id)

        result = await service.get_packs_by_domain(admin, sample_knowledge_domain.id)

        assert sample_knowledge_pack.id not in {p.id for p in result}


class TestGetPackWithDocuments:
    async def test_includes_related_documents(
        self, service, admin, sample_knowledge_pack, classified_document
    ):
        result = await service.get_pack_with_documents(admin, sample_knowledge_pack.id)

        assert classified_document.id in {d.id for d in result.documents}

    async def test_forbidden_for_regular_user(
        self, service, sample_user, sample_knowledge_pack
    ):
        with pytest.raises(ForbiddenError):
            await service.get_pack_with_documents(sample_user, sample_knowledge_pack.id)

    async def test_raises_for_unknown_pack(self, service, admin):
        with pytest.raises(NotFoundError, match="Pack 999999 not found"):
            await service.get_pack_with_documents(admin, 999_999)


class TestArchiveAndRestore:
    async def test_archive_sets_archived_at(self, service, admin, sample_knowledge_pack):
        pack = await service.archive_pack(admin, sample_knowledge_pack.id)
        assert pack.archived_at is not None

    async def test_restore_clears_archived_at(self, service, admin, sample_knowledge_pack):
        await service.archive_pack(admin, sample_knowledge_pack.id)

        pack = await service.restore_pack(admin, sample_knowledge_pack.id)

        assert pack.archived_at is None

    async def test_forbidden_for_regular_user(
        self, service, sample_user, sample_knowledge_pack
    ):
        with pytest.raises(ForbiddenError):
            await service.archive_pack(sample_user, sample_knowledge_pack.id)
        with pytest.raises(ForbiddenError):
            await service.restore_pack(sample_user, sample_knowledge_pack.id)

    async def test_unknown_pack(self, service, admin):
        with pytest.raises(NotFoundError, match="Pack 999999 not found"):
            await service.archive_pack(admin, 999_999)
        with pytest.raises(NotFoundError):
            await service.restore_pack(admin, 999_999)