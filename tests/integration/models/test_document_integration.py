import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from src.db.models.document import Document
from src.db.models.document_chunks import DocumentChunk
from src.db.models.tags import Tag
from src.db.models.knowledge_packs import KnowledgePack
from src.db.enums.document_status import DocumentStatus
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType

pytestmark = pytest.mark.integration


class TestDocumentCompositeUniqueConstraint:

    async def test_duplicate_source_hash_version_raises_integrity_error(
        self, db_session, sample_document
    ):
        duplicate = Document(
            source=sample_document.source,
            document_type=DocumentType.BOOK,
            size=1000,
            content_hash=sample_document.content_hash,
            version=sample_document.version,
            scraped_at=datetime.now(timezone.utc),
            status=DocumentStatus.PENDING,
            embedding_model="text-embedding-3-large",
            knowledge_type=KnowledgeType.REFERENCE,
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_same_source_and_hash_different_version_is_allowed(
        self, db_session, sample_document
    ):
        new_version = Document(
            source=sample_document.source,
            document_type=sample_document.document_type,
            size=sample_document.size,
            content_hash=sample_document.content_hash,
            version=sample_document.version + 1,
            scraped_at=datetime.now(timezone.utc),
            status=DocumentStatus.PENDING,
            embedding_model=sample_document.embedding_model,
            knowledge_type=sample_document.knowledge_type,
        )
        db_session.add(new_version)
        await db_session.commit()
        await db_session.refresh(new_version)

        assert new_version.id is not None
        assert new_version.id != sample_document.id

    async def test_same_source_different_hash_is_allowed(
        self, db_session, sample_document
    ):
        reprocessed = Document(
            source=sample_document.source,
            document_type=sample_document.document_type,
            size=sample_document.size,
            content_hash="c" * 64,
            version=sample_document.version,
            scraped_at=datetime.now(timezone.utc),
            status=DocumentStatus.PENDING,
            embedding_model=sample_document.embedding_model,
            knowledge_type=sample_document.knowledge_type,
        )
        db_session.add(reprocessed)
        await db_session.commit()
        await db_session.refresh(reprocessed)

        assert reprocessed.id is not None


class TestDocumentKnowledgePackRelationship:

    async def test_deleting_knowledge_pack_sets_document_pack_id_null(
        self, db_session, classified_document, sample_knowledge_pack
    ):
        document_id = classified_document.id

        pack_to_delete = await db_session.get(KnowledgePack, sample_knowledge_pack.id)
        await db_session.delete(pack_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(Document)
            .where(Document.id == document_id)
            .execution_options(populate_existing=True)
        )
        reloaded_document = result.scalar_one()
        assert reloaded_document.knowledge_pack_id is None

    async def test_document_without_knowledge_pack_is_allowed(
        self, db_session, sample_document
    ):
        assert sample_document.knowledge_pack_id is None


class TestDocumentChunkIntegrity:

    async def test_duplicate_chunk_index_for_same_document_raises_integrity_error(
        self, db_session, sample_document_chunk, classified_document
    ):
        duplicate_chunk = DocumentChunk(
            document_id=classified_document.id,
            chunk_index=sample_document_chunk.chunk_index,
            qdrant_point_id="point-9999",
            token_count=128,
        )
        db_session.add(duplicate_chunk)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_same_chunk_index_for_different_documents_is_allowed(
        self, db_session, sample_document_chunk, sample_document
    ):
        chunk = DocumentChunk(
            document_id=sample_document.id,
            chunk_index=sample_document_chunk.chunk_index,
            qdrant_point_id="point-0002",
            token_count=256,
        )
        db_session.add(chunk)
        await db_session.commit()
        await db_session.refresh(chunk)

        assert chunk.id is not None

    async def test_duplicate_qdrant_point_id_raises_integrity_error(
        self, db_session, sample_document_chunk, sample_document
    ):
        chunk = DocumentChunk(
            document_id=sample_document.id,
            chunk_index=0,
            qdrant_point_id=sample_document_chunk.qdrant_point_id,
            token_count=256,
        )
        db_session.add(chunk)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_cannot_create_chunk_with_nonexistent_document_id(self, db_session):
        chunk = DocumentChunk(
            document_id=999_999,
            chunk_index=0,
            qdrant_point_id="orphan-point",
            token_count=100,
        )
        db_session.add(chunk)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    async def test_deleting_document_cascades_to_chunks(
        self, db_session, sample_document_chunk, classified_document
    ):
        chunk_id = sample_document_chunk.id
        document_id = classified_document.id

        document_to_delete = await db_session.get(Document, document_id)
        await db_session.delete(document_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(DocumentChunk).where(DocumentChunk.id == chunk_id)
        )
        assert result.scalar_one_or_none() is None


class TestDocumentTagRelationship:

    async def test_document_tag_relationship_persists(
        self, db_session, sample_document, sample_tag, another_tag
    ):
        sample_document.tags.extend([sample_tag, another_tag])
        db_session.add(sample_document)
        await db_session.commit()

        result = await db_session.execute(
            select(Document).where(Document.id == sample_document.id)
        )
        reloaded_document = result.scalar_one()
        assert {t.id for t in reloaded_document.tags} == {sample_tag.id, another_tag.id}

        result = await db_session.execute(
            select(Tag).where(Tag.id == sample_tag.id)
        )
        reloaded_tag = result.scalar_one()
        assert sample_document.id in {d.id for d in reloaded_tag.documents}

    async def test_deleting_document_does_not_delete_tags(
        self, db_session, sample_document, sample_tag
    ):
        sample_document.tags.append(sample_tag)
        db_session.add(sample_document)
        await db_session.commit()
        document_id = sample_document.id

        document_to_delete = await db_session.get(Document, document_id)
        await db_session.delete(document_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(Tag).where(Tag.id == sample_tag.id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_deleting_tag_does_not_delete_document(
        self, db_session, sample_document, sample_tag
    ):
        sample_document.tags.append(sample_tag)
        db_session.add(sample_document)
        await db_session.commit()
        document_id = sample_document.id

        tag_to_delete = await db_session.get(Tag, sample_tag.id)
        await db_session.delete(tag_to_delete)
        await db_session.commit()

        result = await db_session.execute(
            select(Document)
            .where(Document.id == document_id)
            .execution_options(populate_existing=True)
        )
        reloaded_document = result.scalar_one()
        assert reloaded_document.tags == []

    async def test_duplicate_tag_name_raises_integrity_error(self, db_session, sample_tag):
        duplicate = Tag(tag_name=sample_tag.tag_name)
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()