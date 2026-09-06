import pytest

from src.rag.storage.base_vector_store import (
    BaseVectorStorage,
    DenseVector,
    SparseVector,
    VectorPoint,
    VectorSearchResult,
)


class TestVectorSearchResult:

    def test_stores_fields(self):
        result = VectorSearchResult(id="abc", score=0.9, payload={"text": "hello"})

        assert result.id == "abc"
        assert result.score == 0.9
        assert result.payload == {"text": "hello"}


class TestDenseVector:

    def test_stores_values(self):
        vector = DenseVector(values=[0.1, 0.2, 0.3])
        assert vector.values == [0.1, 0.2, 0.3]


class TestSparseVector:

    def test_stores_indices_and_values(self):
        vector = SparseVector(indices=[1, 5], values=[0.5, 0.25])
        assert vector.indices == [1, 5]
        assert vector.values == [0.5, 0.25]


class TestVectorPoint:

    def test_stores_all_fields(self):
        dense = DenseVector(values=[0.1])
        sparse = SparseVector(indices=[1], values=[0.5])
        point = VectorPoint(id="p1", dense=dense, sparse=sparse, payload={"k": "v"})

        assert point.id == "p1"
        assert point.dense is dense
        assert point.sparse is sparse
        assert point.payload == {"k": "v"}


class TestBaseVectorStorage:

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseVectorStorage()

    def test_subclass_missing_methods_cannot_be_instantiated(self):
        class IncompleteStorage(BaseVectorStorage):
            async def upsert(self, point):
                pass

        with pytest.raises(TypeError):
            IncompleteStorage()

    def test_subclass_implementing_all_methods_can_be_instantiated(self):
        class ConcreteStorage(BaseVectorStorage):
            async def upsert(self, point):
                pass

            async def upsert_batch(self, points):
                pass

            async def search_dense(self, vector, limit):
                return []

            async def search_sparse(self, vector, limit):
                return []

            async def delete(self, id):
                pass

            async def exists(self, id):
                return False

        storage = ConcreteStorage()
        assert isinstance(storage, BaseVectorStorage)