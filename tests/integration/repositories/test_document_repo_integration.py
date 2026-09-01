import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.repositories.document_repo import DocumentRepository
from src.db.models.document import Document
from src.db.models.document_chunks import DocumentChunk
from src.db.enums.document_status import DocumentStatus
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType

pytestmark = pytest.mark.integration


@pytest.fixture
def doc_repo(db_session):
    return DocumentRepository(db_session)


class TestDocumentUniqueConstraints:

    async def test_cannot_create_two_documents_with_same_content_hash(
        self, doc_repo, db_session
    ):
        await doc_repo.create(
            source="https://example.com/doc-a.pdf",
            document_type=DocumentType.BOOK,
            size=1024,
            content_hash="c" * 64,
            version=1,
            scraped_at=datetime.now(timezone.utc),
            status=DocumentStatus.PENDING,
            embedding_model="text-embedding-3-large",
            knowledge_type=KnowledgeType.REFERENCE,
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await doc_repo.create(
                source="https://example.com/doc-b.pdf",
                document_type=DocumentType.BOOK,
                size=2048,
                content_hash="c" * 64,
                version=1,
                scraped_at=datetime.now(timezone.utc),
                status=DocumentStatus.PENDING,
                embedding_model="text-embedding-3-large",
                knowledge_type=KnowledgeType.REFERENCE,
            )
            await db_session.commit()

        await db_session.rollback()


class TestDocumentUpdateStatus:

    async def test_update_status_is_persisted(
        self, doc_repo, db_session, sample_document
    ):
        await doc_repo.update_status(sample_document.id, DocumentStatus.INDEXED)
        await db_session.commit()

        doc_id = sample_document.id
        db_session.expire(sample_document)
        reloaded = await doc_repo.get_by_id(doc_id)

        assert reloaded.status == DocumentStatus.INDEXED

    async def test_status_transitions_are_independent(
        self, doc_repo, db_session, sample_document
    ):
        await doc_repo.update_status(sample_document.id, DocumentStatus.INDEXED)
        await db_session.commit()

        await doc_repo.update_status(sample_document.id, DocumentStatus.PENDING)
        await db_session.commit()

        doc_id = sample_document.id
        db_session.expire(sample_document)
        reloaded = await doc_repo.get_by_id(doc_id)

        assert reloaded.status == DocumentStatus.PENDING


class TestDocumentAssignDomain:

    async def test_assign_domain_is_persisted(
        self, doc_repo, db_session, sample_document, sample_knowledge_domain
    ):
        await doc_repo.assign_domain(sample_document.id, sample_knowledge_domain.id)
        await db_session.commit()

        doc_id = sample_document.id
        db_session.expire(sample_document)
        reloaded = await doc_repo.get_by_id(doc_id)

        assert reloaded.domain_id == sample_knowledge_domain.id

    async def test_reassign_domain_overwrites(
        self, doc_repo, db_session, classified_document,
        sample_knowledge_domain, another_knowledge_domain
    ):
        await doc_repo.assign_domain(classified_document.id, another_knowledge_domain.id)
        await db_session.commit()

        doc_id = classified_document.id
        db_session.expire(classified_document)
        reloaded = await doc_repo.get_by_id(doc_id)

        assert reloaded.domain_id == another_knowledge_domain.id

    async def test_assign_domain_does_not_alter_status(
        self, doc_repo, db_session, sample_document, sample_knowledge_domain
    ):
        original_status = sample_document.status

        await doc_repo.assign_domain(sample_document.id, sample_knowledge_domain.id)
        await db_session.commit()

        doc_id = sample_document.id
        db_session.expire(sample_document)
        reloaded = await doc_repo.get_by_id(doc_id)

        assert reloaded.status == original_status


class TestDocumentTagAssociation:

    async def test_add_tag_is_persisted(
        self, doc_repo, db_session, classified_document, sample_tag
    ):
        await doc_repo.add_tag(classified_document, [sample_tag])
        await db_session.commit()

        doc_id = classified_document.id
        domain_id = classified_document.domain_id
        db_session.expire(classified_document)
        reloaded = await doc_repo.get_by_id(doc_id)

        # Eagerly load tags via get_by_domain
        results = await doc_repo.get_by_domain(domain_id)
        doc = next(d for d in results if d.id == doc_id)
        tag_ids = {t.id for t in doc.tags}

        assert sample_tag.id in tag_ids

    async def test_deleting_tag_removes_it_from_document(
        self, doc_repo, db_session, classified_document, sample_tag
    ):
        from src.db.models.tags import Tag

        await doc_repo.add_tag(classified_document, [sample_tag])
        await db_session.commit()

        tag_to_delete = await db_session.get(Tag, sample_tag.id)
        await db_session.delete(tag_to_delete)
        await db_session.commit()

        results = await doc_repo.get_by_domain(classified_document.domain_id)
        doc = next(d for d in results if d.id == classified_document.id)
        tag_ids = {t.id for t in doc.tags}

        assert sample_tag.id not in tag_ids


class TestDocumentDeleteCascade:

    async def test_deleting_document_cascades_chunks(
        self, doc_repo, db_session, classified_document, sample_document_chunk
    ):
        chunk_id = sample_document_chunk.id
        doc_id = classified_document.id

        doc = await db_session.get(Document, doc_id)
        await db_session.delete(doc)
        await db_session.commit()

        result = await db_session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.id == chunk_id)
            .execution_options(populate_existing=True)
        )
        assert result.scalar_one_or_none() is None