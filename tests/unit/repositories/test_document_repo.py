import pytest

from src.repositories.document_repo import DocumentRepository
from src.db.enums.document_status import DocumentStatus

pytestmark = pytest.mark.db


@pytest.fixture
def doc_repo(db_session):
    return DocumentRepository(db_session)


class TestDocumentRepository:

    async def test_get_by_source_found(self, doc_repo, sample_document):
        results = await doc_repo.get_by_source(sample_document.source)

        ids = {d.id for d in results}
        assert sample_document.id in ids

    async def test_get_by_source_empty_for_unknown(self, doc_repo):
        results = await doc_repo.get_by_source("https://notexist.example.com/x.pdf")

        assert results == []

    async def test_get_by_hash_found(self, doc_repo, sample_document):
        found = await doc_repo.get_by_hash(sample_document.content_hash)

        assert found is not None
        assert found.id == sample_document.id

    async def test_get_by_hash_not_found(self, doc_repo):
        found = await doc_repo.get_by_hash("z" * 64)

        assert found is None

    async def test_get_pending_returns_pending_documents(
        self, doc_repo, sample_document
    ):
        results = await doc_repo.get_pending()

        ids = {d.id for d in results}
        assert sample_document.id in ids

    async def test_get_pending_excludes_indexed(
        self, doc_repo, classified_document
    ):
        results = await doc_repo.get_pending()

        ids = {d.id for d in results}
        assert classified_document.id not in ids

    async def test_get_pending_respects_limit(
        self, doc_repo, sample_document
    ):
        results = await doc_repo.get_pending(limit=1)

        assert len(results) <= 1

    async def test_get_by_domain_returns_docs(
        self, doc_repo, classified_document, sample_knowledge_domain
    ):
        results = await doc_repo.get_by_domain(sample_knowledge_domain.id)

        ids = {d.id for d in results}
        assert classified_document.id in ids

    async def test_get_by_domain_empty_for_unknown(self, doc_repo):
        results = await doc_repo.get_by_domain(999999)

        assert results == []

    async def test_update_status_changes_status(self, doc_repo, sample_document):
        updated = await doc_repo.update_status(
            sample_document.id, DocumentStatus.INDEXED
        )

        assert updated.status == DocumentStatus.INDEXED
        assert updated.id == sample_document.id

    async def test_update_status_raises_for_unknown(self, doc_repo):
        with pytest.raises(FileNotFoundError):
            await doc_repo.update_status(999999, DocumentStatus.INDEXED)

    async def test_assign_domain_sets_domain(
        self, doc_repo, sample_document, sample_knowledge_domain
    ):
        updated = await doc_repo.assign_domain(
            sample_document.id, sample_knowledge_domain.id
        )

        assert updated.domain_id == sample_knowledge_domain.id

    async def test_assign_domain_raises_for_unknown(
        self, doc_repo, sample_knowledge_domain
    ):
        with pytest.raises(FileNotFoundError):
            await doc_repo.assign_domain(999999, sample_knowledge_domain.id)

    async def test_add_tag_appends_tags(
        self, doc_repo, classified_document, sample_tag, another_tag
    ):
        updated = await doc_repo.add_tag(classified_document, [sample_tag, another_tag])

        tag_ids = {t.id for t in updated.tags}
        assert sample_tag.id in tag_ids
        assert another_tag.id in tag_ids

    async def test_add_tag_idempotent(
        self, doc_repo, classified_document, sample_tag
    ):
        await doc_repo.add_tag(classified_document, [sample_tag])
        await doc_repo.add_tag(classified_document, [sample_tag])

        count = sum(1 for t in classified_document.tags if t.id == sample_tag.id)
        assert count == 1