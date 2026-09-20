import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.db.models.document_chunks import DocumentChunk

pytestmark = pytest.mark.integration


@pytest.fixture
def chunk_repo(db_session):
    return DocumentChunkRepository(db_session)


class TestDocumentChunkForeignKeyIntegrity:

    async def test_cannot_create_chunk_for_nonexistent_document(
        self, chunk_repo, db_session
    ):
        with pytest.raises(IntegrityError):
            await chunk_repo.create(
                document_id=999_999,
                chunk_index=0,
                qdrant_point_id="pt-orphan",
                token_count=64,
            )
            await db_session.commit()

        await db_session.rollback()


class TestBulkCreatePersistence:

    async def test_bulk_create_all_chunks_persisted(
        self, chunk_repo, db_session, sample_document
    ):
        chunks_data = [
            {"document_id": sample_document.id, "chunk_index": 0, "qdrant_point_id": "int-pt-0", "token_count": 100},
            {"document_id": sample_document.id, "chunk_index": 1, "qdrant_point_id": "int-pt-1", "token_count": 200},
            {"document_id": sample_document.id, "chunk_index": 2, "qdrant_point_id": "int-pt-2", "token_count": 150},
        ]

        created = await chunk_repo.bulk_create(chunks_data)
        await db_session.commit()

        result = await db_session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == sample_document.id)
            .execution_options(populate_existing=True)
        )
        persisted = result.scalars().all()
        persisted_ids = {c.qdrant_point_id for c in persisted}

        assert "int-pt-0" in persisted_ids
        assert "int-pt-1" in persisted_ids
        assert "int-pt-2" in persisted_ids

    async def test_bulk_create_preserves_order(
        self, chunk_repo, db_session, sample_document
    ):
        chunks_data = [
            {"document_id": sample_document.id, "chunk_index": i, "qdrant_point_id": f"ord-pt-{i}", "token_count": 50}
            for i in range(5)
        ]

        await chunk_repo.bulk_create(chunks_data)
        await db_session.commit()

        fetched = await chunk_repo.get_by_document(sample_document.id)
        indices = [c.chunk_index for c in fetched]

        assert indices == sorted(indices)


class TestDeleteForDocument:

    async def test_delete_for_document_removes_all_chunks(
        self, chunk_repo, db_session, sample_document
    ):
        await chunk_repo.bulk_create([
            {"document_id": sample_document.id, "chunk_index": 0, "qdrant_point_id": "del-pt-0", "token_count": 64},
            {"document_id": sample_document.id, "chunk_index": 1, "qdrant_point_id": "del-pt-1", "token_count": 64},
        ])
        await db_session.commit()

        await chunk_repo.delete_for_document(sample_document.id)
        await db_session.commit()

        result = await db_session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == sample_document.id)
            .execution_options(populate_existing=True)
        )
        assert result.scalars().all() == []

    async def test_delete_for_document_does_not_affect_other_documents(
        self, chunk_repo, db_session, sample_document, classified_document, sample_document_chunk
    ):
        await chunk_repo.bulk_create([
            {"document_id": sample_document.id, "chunk_index": 0, "qdrant_point_id": "iso-pt-0", "token_count": 64},
        ])
        await db_session.commit()

        await chunk_repo.delete_for_document(sample_document.id)
        await db_session.commit()

        surviving = await chunk_repo.get_by_document(classified_document.id)
        ids = {c.id for c in surviving}
        assert sample_document_chunk.id in ids