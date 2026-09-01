import pytest

from src.repositories.document_chunk_repo import DocumentChunkRepository

pytestmark = pytest.mark.db


@pytest.fixture
def chunk_repo(db_session):
    return DocumentChunkRepository(db_session)


class TestDocumentChunkRepository:

    async def test_get_by_document_returns_chunks(
        self, chunk_repo, sample_document_chunk, classified_document
    ):
        results = await chunk_repo.get_by_document(classified_document.id)

        ids = {c.id for c in results}
        assert sample_document_chunk.id in ids

    async def test_get_by_document_empty_for_unknown(self, chunk_repo):
        results = await chunk_repo.get_by_document(999999)

        assert results == []

    async def test_get_by_document_ordered_by_index(
        self, chunk_repo, classified_document
    ):
        await chunk_repo.bulk_create([
            {"document_id": classified_document.id, "chunk_index": 2, "qdrant_point_id": "pt-2", "token_count": 100},
            {"document_id": classified_document.id, "chunk_index": 1, "qdrant_point_id": "pt-1", "token_count": 100},
        ])

        results = await chunk_repo.get_by_document(classified_document.id)
        indices = [c.chunk_index for c in results]

        assert indices == sorted(indices)

    async def test_bulk_create_creates_all(self, chunk_repo, sample_document):
        chunks_data = [
            {"document_id": sample_document.id, "chunk_index": 0, "qdrant_point_id": "bulk-0", "token_count": 64},
            {"document_id": sample_document.id, "chunk_index": 1, "qdrant_point_id": "bulk-1", "token_count": 128},
            {"document_id": sample_document.id, "chunk_index": 2, "qdrant_point_id": "bulk-2", "token_count": 96},
        ]

        created = await chunk_repo.bulk_create(chunks_data)

        assert len(created) == 3
        assert all(c.id is not None for c in created)

    async def test_delete_for_document_removes_chunks(
        self, chunk_repo, classified_document, sample_document_chunk
    ):
        await chunk_repo.delete_for_document(classified_document.id)

        remaining = await chunk_repo.get_by_document(classified_document.id)
        assert remaining == []

    async def test_delete_for_document_noop_on_empty(
        self, chunk_repo, sample_document
    ):
        # Should not raise even when there's nothing to delete
        await chunk_repo.delete_for_document(sample_document.id)

        remaining = await chunk_repo.get_by_document(sample_document.id)
        assert remaining == []