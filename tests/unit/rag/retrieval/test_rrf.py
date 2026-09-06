import pytest

from src.rag.retrieval.rrf import RRF
from src.rag.storage.base_vector_store import VectorSearchResult


def make_result(id_, score=0.0, payload=None):
    return VectorSearchResult(id=id_, score=score, payload=payload or {"text": id_})


class TestFuse:

    def test_empty_inputs_return_empty_list(self):
        rrf = RRF()
        assert rrf.fuse([], []) == []

    def test_single_list_dense_only(self):
        rrf = RRF()
        dense = [make_result("a"), make_result("b")]

        result = rrf.fuse(dense, [])

        assert [r.id for r in result] == ["a", "b"]

    def test_single_list_sparse_only(self):
        rrf = RRF()
        sparse = [make_result("a"), make_result("b")]

        result = rrf.fuse([], sparse)

        assert [r.id for r in result] == ["a", "b"]

    def test_document_appearing_in_both_lists_gets_combined_score(self):
        rrf = RRF()
        dense = [make_result("a")]
        sparse = [make_result("a")]

        result = rrf.fuse(dense, sparse, k=60)

        assert len(result) == 1
        assert result[0].id == "a"
        assert result[0].score == pytest.approx(1 / 60 + 1 / 60)

    def test_document_only_in_one_list_gets_single_contribution(self):
        rrf = RRF()
        dense = [make_result("a")]
        sparse = [make_result("b")]

        result = rrf.fuse(dense, sparse, k=60)

        scores = {r.id: r.score for r in result}
        assert scores["a"] == pytest.approx(1 / 60)
        assert scores["b"] == pytest.approx(1 / 60)

    def test_results_are_sorted_by_fused_score_descending(self):
        rrf = RRF()
        # "shared" appears in both lists at rank 0, so it should out-rank
        # anything that only appears in a single list.
        dense = [make_result("only_dense"), make_result("shared")]
        sparse = [make_result("shared"), make_result("only_sparse")]

        result = rrf.fuse(dense, sparse, k=60)

        assert result[0].id == "shared"

    def test_rank_position_affects_score(self):
        rrf = RRF()
        dense = [make_result("first"), make_result("second"), make_result("third")]

        result = rrf.fuse(dense, [], k=60)
        scores = {r.id: r.score for r in result}

        assert scores["first"] > scores["second"] > scores["third"]

    def test_smaller_k_increases_score_magnitude(self):
        rrf = RRF()
        dense = [make_result("a")]

        result_small_k = rrf.fuse(dense, [], k=1)
        result_large_k = rrf.fuse(dense, [], k=1000)

        assert result_small_k[0].score > result_large_k[0].score

    def test_default_k_is_sixty(self):
        rrf = RRF()
        dense = [make_result("a")]

        result = rrf.fuse(dense, [])

        assert result[0].score == pytest.approx(1 / 60)

    def test_payload_is_preserved_from_original_result(self):
        rrf = RRF()
        dense = [make_result("a", payload={"text": "hello", "source": "doc.txt"})]

        result = rrf.fuse(dense, [])

        assert result[0].payload == {"text": "hello", "source": "doc.txt"}

    def test_sparse_result_payload_used_when_only_in_sparse_list(self):
        rrf = RRF()
        sparse = [make_result("a", payload={"text": "sparse only"})]

        result = rrf.fuse([], sparse)

        assert result[0].payload == {"text": "sparse only"}

    def test_dense_payload_overridden_by_sparse_when_id_appears_in_both(self):
        # docs[result.id] is overwritten by whichever list is processed
        # last (sparse), so the final payload comes from the sparse result.
        rrf = RRF()
        dense = [make_result("a", payload={"text": "from dense"})]
        sparse = [make_result("a", payload={"text": "from sparse"})]

        result = rrf.fuse(dense, sparse)

        assert result[0].payload == {"text": "from sparse"}