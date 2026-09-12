from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.storage.base_vector_store import (
    DenseVector,
    SparseVector,
    VectorPoint,
    VectorSearchResult,
)
from src.rag.storage.vector_store import QdrantVectorSearch
from src.rag.retrieval.dense_search import DenseSearch
from src.rag.retrieval.sparse_search import SparseSearch
from src.rag.retrieval.rrf import RRF
from src.rag.retrieval.reranker import Reranker
from src.rag.retrieval.retrieval import Retrieval
from src.rag.retrieval.query_encoder import QueryEncoder
from src.rag.embeddings.bge_m3 import EmbeddingResult
from src.rag.rag_schemas.search_filter import SearchFilter

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(id_: str, score: float, text: str = "some text") -> VectorSearchResult:
    return VectorSearchResult(id=id_, score=score, payload={"text": text})


def make_embedding_result(
    dense_values: list[float] | None = None,
    sparse_indices: list[int] | None = None,
    sparse_values: list[float] | None = None,
) -> EmbeddingResult:
    return EmbeddingResult(
        dense=DenseVector(values=dense_values or [0.1, 0.2, 0.3]),
        sparse=SparseVector(
            indices=sparse_indices or [1, 4],
            values=sparse_values or [0.7, 0.3],
        ),
    )


# ---------------------------------------------------------------------------
# RRF
# ---------------------------------------------------------------------------

class TestRRF:

    def test_fuse_combines_overlapping_results_by_adding_scores(self):
        rrf = RRF()
        dense = [make_result("a", 0.9), make_result("b", 0.8)]
        sparse = [make_result("b", 5.0), make_result("c", 4.0)]

        fused = rrf.fuse(dense, sparse, k=60)
        fused_ids = [r.id for r in fused]

        # "b" appears in both lists -> highest combined RRF score -> first
        assert fused_ids[0] == "b"
        assert set(fused_ids) == {"a", "b", "c"}

    def test_fuse_score_is_reciprocal_rank_sum(self):
        rrf = RRF()
        dense = [make_result("a", 0.9)]
        sparse = [make_result("a", 5.0)]

        fused = rrf.fuse(dense, sparse, k=60)

        assert fused[0].id == "a"
        assert fused[0].score == pytest.approx(1 / 60 + 1 / 60)

    def test_fuse_preserves_payload_from_last_seen_occurrence(self):
        rrf = RRF()
        dense = [make_result("a", 0.9, text="dense payload")]
        sparse = [make_result("a", 5.0, text="sparse payload")]

        fused = rrf.fuse(dense, sparse, k=60)

        # sparse is processed last -> its payload wins
        assert fused[0].payload["text"] == "sparse payload"

    def test_fuse_handles_empty_inputs(self):
        rrf = RRF()
        assert rrf.fuse([], [], k=60) == []
        assert rrf.fuse([make_result("a", 1.0)], [], k=60)[0].id == "a"


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------

class TestReranker:

    @pytest.fixture(autouse=True)
    def _patch_reranker_model(self, monkeypatch):
        monkeypatch.setattr(
            "src.rag.retrieval.reranker.FlagReranker",
            lambda *args, **kwargs: MagicMock(),
        )

    def test_rerank_orders_by_score_descending_and_limits_to_top_n(self):
        reranker = Reranker(top_n=5)
        reranker.model.compute_score = MagicMock(return_value=[0.2, 0.9, 0.5])
        results = [make_result("a", 0), make_result("b", 0), make_result("c", 0)]

        reranked = reranker.rerank("query", results, top_n=2)

        assert [r.id for r in reranked] == ["b", "c"]
        assert reranked[0].score == pytest.approx(0.9)

    def test_rerank_uses_default_top_n_when_not_overridden(self):
        reranker = Reranker(top_n=1)
        reranker.model.compute_score = MagicMock(return_value=[0.1, 0.9])
        results = [make_result("a", 0), make_result("b", 0)]

        reranked = reranker.rerank("query", results)

        assert [r.id for r in reranked] == ["b"]

    def test_rerank_returns_empty_list_for_empty_input(self):
        reranker = Reranker()
        reranker.model.compute_score = MagicMock()

        assert reranker.rerank("query", []) == []
        reranker.model.compute_score.assert_not_called()

    def test_rerank_handles_single_float_score(self):
        reranker = Reranker()
        reranker.model.compute_score = MagicMock(return_value=0.42)

        reranked = reranker.rerank("query", [make_result("a", 0)])

        assert reranked[0].score == pytest.approx(0.42)

    def test_rerank_handles_none_scores_as_zero(self):
        reranker = Reranker()
        reranker.model.compute_score = MagicMock(return_value=None)
        results = [make_result("a", 0), make_result("b", 0)]

        reranked = reranker.rerank("query", results)

        assert {r.score for r in reranked} == {0.0}


# ---------------------------------------------------------------------------
# DenseSearch
# DenseSearch(vector_store) — no longer owns an embedding model.
# Caller passes a pre-encoded DenseVector to .search().
# ---------------------------------------------------------------------------

class TestDenseSearch:

    @pytest.fixture
    def vector_store(self):
        store = MagicMock()
        store.search_dense = AsyncMock(return_value=[make_result("a", 1.0)])
        return store

    @pytest.fixture
    def dense_search(self, vector_store):
        return DenseSearch(vector_store=vector_store)

    @pytest.mark.asyncio
    async def test_delegates_pre_encoded_vector_to_vector_store(
        self, dense_search, vector_store
    ):
        vector = make_embedding_result().dense

        results = await dense_search.search(vector, limit=10)

        vector_store.search_dense.assert_awaited_once_with(
            vector=vector, limit=10, filters=None
        )
        assert results[0].id == "a"

    @pytest.mark.asyncio
    async def test_passes_filters_through_to_vector_store(
        self, dense_search, vector_store
    ):
        vector = make_embedding_result().dense
        filters = SearchFilter(language="en", domains=["ml"])

        await dense_search.search(vector, limit=5, filters=filters)

        vector_store.search_dense.assert_awaited_once_with(
            vector=vector, limit=5, filters=filters
        )

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_store_finds_nothing(
        self, dense_search, vector_store
    ):
        vector_store.search_dense.return_value = []

        results = await dense_search.search(make_embedding_result().dense, limit=5)

        assert results == []


# ---------------------------------------------------------------------------
# SparseSearch
# Same structural change as DenseSearch — no embedding, accepts SparseVector.
# ---------------------------------------------------------------------------

class TestSparseSearch:

    @pytest.fixture
    def vector_store(self):
        store = MagicMock()
        store.search_sparse = AsyncMock(return_value=[make_result("b", 1.0)])
        return store

    @pytest.fixture
    def sparse_search(self, vector_store):
        return SparseSearch(vector_store=vector_store)

    @pytest.mark.asyncio
    async def test_delegates_pre_encoded_vector_to_vector_store(
        self, sparse_search, vector_store
    ):
        vector = make_embedding_result().sparse

        results = await sparse_search.search(vector, limit=10)

        vector_store.search_sparse.assert_awaited_once_with(
            vector=vector, limit=10, filters=None
        )
        assert results[0].id == "b"

    @pytest.mark.asyncio
    async def test_passes_filters_through_to_vector_store(
        self, sparse_search, vector_store
    ):
        vector = make_embedding_result().sparse
        filters = SearchFilter(language="uk", knowledge_packs=["backend"])

        await sparse_search.search(vector, limit=5, filters=filters)

        vector_store.search_sparse.assert_awaited_once_with(
            vector=vector, limit=5, filters=filters
        )

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_store_finds_nothing(
        self, sparse_search, vector_store
    ):
        vector_store.search_sparse.return_value = []

        results = await sparse_search.search(make_embedding_result().sparse, limit=5)

        assert results == []


# ---------------------------------------------------------------------------
# Retrieval
# Now owns a QueryEncoder. retrieve() encodes the query string first,
# then passes the resulting dense/sparse vectors into DenseSearch/SparseSearch.
# Both search calls also receive the optional filters argument.
# ---------------------------------------------------------------------------

class TestRetrieval:

    @pytest.fixture
    def encoded_query(self):
        return make_embedding_result()

    @pytest.fixture
    def mock_query_encoder(self, encoded_query):
        encoder = MagicMock()
        encoder.encode = MagicMock(return_value=encoded_query)
        return encoder

    @pytest.fixture
    def dense_search(self, encoded_query):
        return MagicMock(
            search=AsyncMock(return_value=[
                make_result("a", 0.9),
                make_result("b", 0.8),
            ])
        )

    @pytest.fixture
    def sparse_search(self, encoded_query):
        return MagicMock(
            search=AsyncMock(return_value=[
                make_result("b", 5.0),
                make_result("c", 4.0),
            ])
        )

    @pytest.fixture
    def reranker(self):
        # Identity reranker so we can assert what Retrieval fed it,
        # without depending on Reranker's own (separately tested) logic.
        return MagicMock(
            rerank=MagicMock(side_effect=lambda query, results, top_n: results[:top_n])
        )

    @pytest.fixture
    def retrieval(self, mock_query_encoder, dense_search, sparse_search, reranker):
        return Retrieval(
            query_encoder=mock_query_encoder,
            sparse_search=sparse_search,
            dense_search=dense_search,
            rrf=RRF(),
            reranker=reranker,
        )

    @pytest.mark.asyncio
    async def test_encodes_query_before_searching(
        self, retrieval, mock_query_encoder
    ):
        await retrieval.retrieve(query="test query", limit=10, top_n=3)

        mock_query_encoder.encode.assert_called_once_with("test query")

    @pytest.mark.asyncio
    async def test_passes_encoded_vectors_to_dense_and_sparse_search(
        self, retrieval, mock_query_encoder, dense_search, sparse_search, encoded_query
    ):
        await retrieval.retrieve(query="test query", limit=10, top_n=3)

        dense_search.search.assert_awaited_once_with(
            encoded_query.dense, 10, None
        )
        sparse_search.search.assert_awaited_once_with(
            encoded_query.sparse, 10, None
        )

    @pytest.mark.asyncio
    async def test_passes_filters_to_both_searches(
        self, retrieval, dense_search, sparse_search
    ):
        filters = SearchFilter(language="en", domains=["engineering"])

        await retrieval.retrieve(query="q", limit=5, top_n=2, filters=filters)

        assert dense_search.search.call_args.args[2] is filters
        assert sparse_search.search.call_args.args[2] is filters

    @pytest.mark.asyncio
    async def test_fuses_results_before_reranking(
        self, retrieval, reranker
    ):
        await retrieval.retrieve(query="test query", limit=10, top_n=3)

        reranker.rerank.assert_called_once()
        fused = reranker.rerank.call_args.args[1]
        fused_ids = [r.id for r in fused]
        # "b" in both lists -> highest RRF score -> first
        assert fused_ids[0] == "b"
        assert set(fused_ids) == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_passes_custom_k_to_rrf(
        self, mock_query_encoder, dense_search, sparse_search, reranker
    ):
        rrf = MagicMock(fuse=MagicMock(return_value=[]))
        retrieval = Retrieval(
            query_encoder=mock_query_encoder,
            sparse_search=sparse_search,
            dense_search=dense_search,
            rrf=rrf,
            reranker=reranker,
        )

        await retrieval.retrieve(query="q", limit=10, top_n=3, k=25)

        assert rrf.fuse.call_args.args[2] == 25

    @pytest.mark.asyncio
    async def test_returns_reranked_results(self, retrieval):
        results = await retrieval.retrieve(query="test query", limit=10, top_n=2)

        assert len(results) == 2
        assert all(isinstance(r, VectorSearchResult) for r in results)

    @pytest.mark.asyncio
    async def test_propagates_dense_search_failure(
        self, mock_query_encoder, sparse_search, reranker
    ):
        failing_dense = MagicMock(
            search=AsyncMock(side_effect=RuntimeError("qdrant down"))
        )
        retrieval = Retrieval(
            query_encoder=mock_query_encoder,
            sparse_search=sparse_search,
            dense_search=failing_dense,
            rrf=RRF(),
            reranker=reranker,
        )

        with pytest.raises(RuntimeError, match="qdrant down"):
            await retrieval.retrieve(query="q", limit=10, top_n=3)


# ---------------------------------------------------------------------------
# QdrantVectorSearch
# ---------------------------------------------------------------------------

class TestQdrantVectorSearch:

    @pytest.fixture
    def client(self):
        client = MagicMock()
        client.upsert = AsyncMock()
        client.delete = AsyncMock()
        client.retrieve = AsyncMock(return_value=[])
        client.collection_exists = AsyncMock(return_value=True)
        client.create_collection = AsyncMock()
        client.create_payload_index = AsyncMock()
        client.query_points = AsyncMock()
        return client

    @pytest.fixture
    def store(self, client):
        return QdrantVectorSearch(client=client, collection_name="knowledge")

    # --- upsert_batch ---

    @pytest.mark.asyncio
    async def test_upsert_batch_builds_points_with_dense_and_sparse_vectors(
        self, store, client
    ):
        points = [
            VectorPoint(
                id="p1",
                dense=DenseVector(values=[0.1, 0.2]),
                sparse=SparseVector(indices=[0, 3], values=[0.5, 0.4]),
                payload={"document_id": 1, "text": "hello"},
            )
        ]

        await store.upsert_batch(points)

        client.upsert.assert_awaited_once()
        kwargs = client.upsert.await_args.kwargs
        assert kwargs["collection_name"] == "knowledge"
        sent_point = kwargs["points"][0]
        assert sent_point.id == "p1"
        assert sent_point.vector["dense"] == [0.1, 0.2]
        assert sent_point.vector["sparse"].indices == [0, 3]
        assert sent_point.vector["sparse"].values == [0.5, 0.4]
        assert sent_point.payload == {"document_id": 1, "text": "hello"}

    @pytest.mark.asyncio
    async def test_upsert_batch_sends_all_points_in_one_call(self, store, client):
        points = [
            VectorPoint(
                id=f"p{i}",
                dense=DenseVector(values=[float(i)]),
                sparse=SparseVector(indices=[i], values=[1.0]),
                payload={},
            )
            for i in range(3)
        ]

        await store.upsert_batch(points)

        client.upsert.assert_awaited_once()
        assert len(client.upsert.await_args.kwargs["points"]) == 3

    # --- upsert ---

    @pytest.mark.asyncio
    async def test_upsert_delegates_to_upsert_batch_with_single_item_list(
        self, store, client
    ):
        point = VectorPoint(
            id="p1",
            dense=DenseVector(values=[0.1]),
            sparse=SparseVector(indices=[0], values=[1.0]),
            payload={},
        )

        await store.upsert(point)

        client.upsert.assert_awaited_once()
        assert len(client.upsert.await_args.kwargs["points"]) == 1

    # --- ensure_collection ---

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_when_missing(self, store, client):
        client.collection_exists.return_value = False

        await store.ensure_collection()

        client.create_collection.assert_awaited_once()
        kwargs = client.create_collection.await_args.kwargs
        assert kwargs["collection_name"] == "knowledge"
        assert "dense" in kwargs["vectors_config"]
        assert "sparse" in kwargs["sparse_vectors_config"]

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_payload_indexes_for_all_fields(
        self, store, client
    ):
        client.collection_exists.return_value = False

        await store.ensure_collection()

        indexed = {
            call.kwargs["field_name"]
            for call in client.create_payload_index.await_args_list
        }
        assert indexed == {
            "knowledge_pack", "domain", "language", "framework", "source_type", "tags"
        }

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_creation_when_already_exists(
        self, store, client
    ):
        client.collection_exists.return_value = True

        await store.ensure_collection()

        client.create_collection.assert_not_awaited()

    # --- search_dense ---

    @pytest.mark.asyncio
    async def test_search_dense_maps_query_points_to_vector_search_results(
        self, store, client
    ):
        point = MagicMock(id="doc-1", score=0.87, payload={"text": "hi"})
        client.query_points.return_value = MagicMock(points=[point])

        results = await store.search_dense(
            vector=DenseVector(values=[0.1, 0.2]), limit=5
        )

        kwargs = client.query_points.await_args.kwargs
        assert kwargs["using"] == "dense"
        assert kwargs["query"] == [0.1, 0.2]
        assert kwargs["limit"] == 5
        assert results == [
            VectorSearchResult(id="doc-1", score=0.87, payload={"text": "hi"})
        ]

    @pytest.mark.asyncio
    async def test_search_dense_defaults_missing_payload_to_empty_dict(
        self, store, client
    ):
        point = MagicMock(id="doc-1", score=0.5, payload=None)
        client.query_points.return_value = MagicMock(points=[point])

        results = await store.search_dense(
            vector=DenseVector(values=[0.1]), limit=1
        )

        assert results[0].payload == {}

    @pytest.mark.asyncio
    async def test_search_dense_passes_built_filter_to_client(
        self, store, client
    ):
        client.query_points.return_value = MagicMock(points=[])
        filters = SearchFilter(language="en")

        await store.search_dense(
            vector=DenseVector(values=[0.1, 0.2]), limit=5, filters=filters
        )

        kwargs = client.query_points.await_args.kwargs
        # _build_qdrant_filter converts SearchFilter -> qdrant Filter object
        assert kwargs["query_filter"] is not None

    @pytest.mark.asyncio
    async def test_search_dense_passes_none_filter_when_no_filters(
        self, store, client
    ):
        client.query_points.return_value = MagicMock(points=[])

        await store.search_dense(vector=DenseVector(values=[0.1]), limit=5)

        kwargs = client.query_points.await_args.kwargs
        assert kwargs["query_filter"] is None

    # --- search_sparse ---

    @pytest.mark.asyncio
    async def test_search_sparse_maps_query_points_to_vector_search_results(
        self, store, client
    ):
        point = MagicMock(id="doc-2", score=0.42, payload={"text": "yo"})
        client.query_points.return_value = MagicMock(points=[point])

        results = await store.search_sparse(
            vector=SparseVector(indices=[1, 2], values=[0.9, 0.1]), limit=3
        )

        kwargs = client.query_points.await_args.kwargs
        assert kwargs["using"] == "sparse"
        assert kwargs["query"].indices == [1, 2]
        assert kwargs["query"].values == [0.9, 0.1]
        assert results[0].id == "doc-2"

    @pytest.mark.asyncio
    async def test_search_sparse_defaults_missing_payload_to_empty_dict(
        self, store, client
    ):
        point = MagicMock(id="doc-2", score=0.3, payload=None)
        client.query_points.return_value = MagicMock(points=[point])

        results = await store.search_sparse(
            vector=SparseVector(indices=[1], values=[0.5]), limit=1
        )

        assert results[0].payload == {}

    @pytest.mark.asyncio
    async def test_search_sparse_passes_built_filter_to_client(
        self, store, client
    ):
        client.query_points.return_value = MagicMock(points=[])
        filters = SearchFilter(knowledge_packs=["docs"])

        await store.search_sparse(
            vector=SparseVector(indices=[1], values=[0.5]), limit=5, filters=filters
        )

        kwargs = client.query_points.await_args.kwargs
        assert kwargs["query_filter"] is not None

    # --- delete ---

    @pytest.mark.asyncio
    async def test_delete_calls_client_with_point_ids_list(self, store, client):
        await store.delete("p1")

        client.delete.assert_awaited_once()
        kwargs = client.delete.await_args.kwargs
        assert kwargs["collection_name"] == "knowledge"
        assert kwargs["points_selector"].points == ["p1"]

    # --- exists ---

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_point_found(self, store, client):
        client.retrieve.return_value = [MagicMock()]

        assert await store.exists("p1") is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_point_missing(self, store, client):
        client.retrieve.return_value = []

        assert await store.exists("missing") is False

    # --- _build_qdrant_filter ---

    def test_build_filter_returns_none_when_no_filters(self, store):
        assert store._build_qdrant_filter(None) is None

    def test_build_filter_returns_none_when_all_fields_are_none(self, store):
        filters = SearchFilter()
        assert store._build_qdrant_filter(filters) is None

    def test_build_filter_includes_list_field_as_match_any(self, store):
        filters = SearchFilter(knowledge_packs=["pack-a", "pack-b"])
        result = store._build_qdrant_filter(filters)

        assert result is not None
        condition = result.must[0]
        assert condition.key == "knowledge_pack"
        assert condition.match.any == ["pack-a", "pack-b"]

    def test_build_filter_includes_scalar_field_as_match_value(self, store):
        filters = SearchFilter(language="en")
        result = store._build_qdrant_filter(filters)

        assert result is not None
        condition = result.must[0]
        assert condition.key == "language"
        assert condition.match.value == "en"

    def test_build_filter_combines_multiple_conditions(self, store):
        filters = SearchFilter(language="uk", domains=["backend"], tags=["python"])
        result = store._build_qdrant_filter(filters)

        assert result is not None
        assert len(result.must) == 3

    def test_build_filter_ignores_none_valued_fields(self, store):
        filters = SearchFilter(language="en", framework=None, source_type=None)
        result = store._build_qdrant_filter(filters)

        assert result is not None
        assert len(result.must) == 1