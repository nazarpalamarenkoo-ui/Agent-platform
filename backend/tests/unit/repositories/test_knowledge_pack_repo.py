from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import InvalidRequestError

from src.repositories.knowledge_pack_repo import KnowledgePackRepository

pytestmark = pytest.mark.db


def archived():
    return datetime.now(timezone.utc)


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


class TestActiveQueries:

    async def test_list_active_excludes_archived_and_orders_by_name(
        self, pack_repo, make_pack, sample_knowledge_domain
    ):
        await make_pack(sample_knowledge_domain, name="b-pack")
        await make_pack(sample_knowledge_domain, name="a-pack")
        await make_pack(sample_knowledge_domain, name="old-pack", archived_at=archived())

        result = await pack_repo.list_active()

        assert [p.name for p in result] == ["a-pack", "b-pack"]

    async def test_list_active_filters_by_domain_and_paginates(
        self, pack_repo, make_pack, sample_knowledge_domain, another_knowledge_domain
    ):
        await make_pack(sample_knowledge_domain, name="a-pack")
        await make_pack(sample_knowledge_domain, name="b-pack")
        await make_pack(sample_knowledge_domain, name="c-pack")
        await make_pack(another_knowledge_domain, name="z-pack")

        page = await pack_repo.list_active(
            limit=2, offset=1, domain_id=sample_knowledge_domain.id
        )

        assert [p.name for p in page] == ["b-pack", "c-pack"]

    async def test_get_active_ignores_archived(
        self, pack_repo, make_pack, sample_knowledge_domain
    ):
        active = await make_pack(sample_knowledge_domain)
        old = await make_pack(sample_knowledge_domain, archived_at=archived())

        assert (await pack_repo.get_active(active.id)).id == active.id
        assert await pack_repo.get_active(old.id) is None

    async def test_get_active_many_dedupes_and_skips_archived(
        self, pack_repo, make_pack, sample_knowledge_domain
    ):
        active = await make_pack(sample_knowledge_domain)
        old = await make_pack(sample_knowledge_domain, archived_at=archived())

        result = await pack_repo.get_active_many([active.id, active.id, old.id])

        assert [p.id for p in result] == [active.id]
        assert await pack_repo.get_active_many([]) == []

    async def test_active_queries_do_not_allow_loading_documents(
        self, db_session, pack_repo, make_pack, sample_knowledge_domain
    ):
        pack = await make_pack(sample_knowledge_domain)
        pack_id = pack.id
        db_session.expunge_all()

        from_list = (await pack_repo.list_active())[0]
        with pytest.raises(InvalidRequestError):
            from_list.documents

        db_session.expunge_all()
        from_get = await pack_repo.get_active(pack_id)
        with pytest.raises(InvalidRequestError):
            from_get.documents

    async def test_list_candidates_returns_active_rows_ordered_by_id(
        self, pack_repo, make_pack, sample_knowledge_domain
    ):
        first = await make_pack(sample_knowledge_domain, description="first")
        second = await make_pack(sample_knowledge_domain, description="second")
        await make_pack(sample_knowledge_domain, archived_at=archived())

        rows = await pack_repo.list_candidates()

        assert [(r.id, r.description) for r in rows] == [
            (first.id, "first"),
            (second.id, "second"),
        ]


class TestBundleQueries:

    @pytest.fixture
    async def bundle_with_packs(
        self, db_session, make_user, make_agent, make_bundle, make_pack,
        sample_knowledge_domain
    ):
        bundle = await make_bundle(await make_user(), await make_agent())
        pack_b = await make_pack(sample_knowledge_domain, slug="b-slug", version=2)
        pack_a = await make_pack(
            sample_knowledge_domain, slug="a-slug", archived_at=archived()
        )
        outside = await make_pack(sample_knowledge_domain, slug="outside")
        bundle.knowledge_packs.extend([pack_b, pack_a])
        await db_session.commit()
        return dict(bundle=bundle, pack_a=pack_a, pack_b=pack_b, outside=outside)

    async def test_list_for_bundle_includes_archived_and_orders_by_id(
        self, pack_repo, bundle_with_packs
    ):
        result = await pack_repo.list_for_bundle(bundle_with_packs["bundle"].id)

        ids = [p.id for p in result]
        assert set(ids) == {bundle_with_packs["pack_a"].id, bundle_with_packs["pack_b"].id}
        assert ids == sorted(ids)

    async def test_list_slugs_for_bundle_is_sorted(self, pack_repo, bundle_with_packs):
        slugs = await pack_repo.list_slugs_for_bundle(bundle_with_packs["bundle"].id)

        assert slugs == ["a-slug", "b-slug"]

    async def test_manifest_has_version_and_archive_flag(self, pack_repo, bundle_with_packs):
        rows = await pack_repo.list_manifest_for_bundle(bundle_with_packs["bundle"].id)

        by_slug = {r.slug: r for r in rows}
        assert set(by_slug) == {"a-slug", "b-slug"}
        assert by_slug["b-slug"].version == 2
        assert by_slug["b-slug"].archived_at is None
        assert by_slug["a-slug"].archived_at is not None

    async def test_bundle_queries_are_empty_for_bundle_without_packs(
        self, pack_repo, make_user, make_agent, make_bundle
    ):
        bundle = await make_bundle(await make_user(), await make_agent())

        assert await pack_repo.list_for_bundle(bundle.id) == []
        assert await pack_repo.list_slugs_for_bundle(bundle.id) == []
        assert await pack_repo.list_manifest_for_bundle(bundle.id) == []


class TestArchiveAndRestore:

    async def test_archive_sets_timestamp_once(
        self, pack_repo, make_pack, sample_knowledge_domain
    ):
        pack = await make_pack(sample_knowledge_domain)

        await pack_repo.archive(pack)
        first = pack.archived_at
        await pack_repo.archive(pack)

        assert first is not None
        assert pack.archived_at == first

    async def test_restore_clears_timestamp(
        self, pack_repo, make_pack, sample_knowledge_domain
    ):
        pack = await make_pack(sample_knowledge_domain, archived_at=archived())

        await pack_repo.restore(pack)

        assert pack.archived_at is None