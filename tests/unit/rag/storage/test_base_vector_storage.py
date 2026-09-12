import pytest

from src.rag.storage.base_vector_store import (
    BaseVectorStorage,
    DenseVector,
    SparseVector,
    VectorPoint,
    VectorSearchResult,
)
from src.rag.rag_schemas.search_filter import SearchFilter

class TestVectorSearchResult:

    def test_stores_fields(self):
        result = VectorSearchResult(id="abc", score=0.9, payload={"text": "hello"})

        assert result.id == "abc"
        assert result.score == 0.9
        assert result.payload == {"text": "hello"}

    def test_equality_by_value(self):
        r1 = VectorSearchResult(id="x", score=0.5, payload={})
        r2 = VectorSearchResult(id="x", score=0.5, payload={})
        assert r1 == r2

    def test_inequality_on_different_id(self):
        r1 = VectorSearchResult(id="a", score=0.5, payload={})
        r2 = VectorSearchResult(id="b", score=0.5, payload={})
        assert r1 != r2


class TestDenseVector:

    def test_stores_values(self):
        vector = DenseVector(values=[0.1, 0.2, 0.3])
        assert vector.values == [0.1, 0.2, 0.3]

    def test_empty_values(self):
        vector = DenseVector(values=[])
        assert vector.values == []

    def test_equality_by_value(self):
        assert DenseVector(values=[0.1]) == DenseVector(values=[0.1])


class TestSparseVector:

    def test_stores_indices_and_values(self):
        vector = SparseVector(indices=[1, 5], values=[0.5, 0.25])
        assert vector.indices == [1, 5]
        assert vector.values == [0.5, 0.25]

    def test_empty_sparse_vector(self):
        vector = SparseVector(indices=[], values=[])
        assert vector.indices == []
        assert vector.values == []

    def test_equality_by_value(self):
        v1 = SparseVector(indices=[1], values=[0.5])
        v2 = SparseVector(indices=[1], values=[0.5])
        assert v1 == v2


class TestVectorPoint:

    def test_stores_all_fields(self):
        dense = DenseVector(values=[0.1])
        sparse = SparseVector(indices=[1], values=[0.5])
        point = VectorPoint(id="p1", dense=dense, sparse=sparse, payload={"k": "v"})

        assert point.id == "p1"
        assert point.dense is dense
        assert point.sparse is sparse
        assert point.payload == {"k": "v"}

    def test_equality_by_value(self):
        dense = DenseVector(values=[0.1])
        sparse = SparseVector(indices=[1], values=[0.5])
        p1 = VectorPoint(id="x", dense=dense, sparse=sparse, payload={})
        p2 = VectorPoint(id="x", dense=dense, sparse=sparse, payload={})
        assert p1 == p2

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

            async def search_dense(self, vector, limit, filters=None):
                return []

            async def search_sparse(self, vector, limit, filters=None):
                return []

            async def delete(self, id):
                pass

            async def exists(self, id):
                return False

        storage = ConcreteStorage()
        assert isinstance(storage, BaseVectorStorage)

    def test_search_dense_accepts_filters_kwarg(self):
        class ConcreteStorage(BaseVectorStorage):
            async def upsert(self, point): pass
            async def upsert_batch(self, points): pass
            async def search_dense(self, vector, limit, filters=None): return []
            async def search_sparse(self, vector, limit, filters=None): return []
            async def delete(self, id): pass
            async def exists(self, id): return False

        import inspect
        sig = inspect.signature(ConcreteStorage.search_dense)
        assert "filters" in sig.parameters

    def test_search_sparse_accepts_filters_kwarg(self):
        class ConcreteStorage(BaseVectorStorage):
            async def upsert(self, point): pass
            async def upsert_batch(self, points): pass
            async def search_dense(self, vector, limit, filters=None): return []
            async def search_sparse(self, vector, limit, filters=None): return []
            async def delete(self, id): pass
            async def exists(self, id): return False

        import inspect
        sig = inspect.signature(ConcreteStorage.search_sparse)
        assert "filters" in sig.parameters

    def test_subclass_without_delete_cannot_be_instantiated(self):
        class MissingDelete(BaseVectorStorage):
            async def upsert(self, point): pass
            async def upsert_batch(self, points): pass
            async def search_dense(self, vector, limit, filters=None): return []
            async def search_sparse(self, vector, limit, filters=None): return []
            async def exists(self, id): return False

        with pytest.raises(TypeError):
            MissingDelete()

    def test_subclass_without_exists_cannot_be_instantiated(self):
        class MissingExists(BaseVectorStorage):
            async def upsert(self, point): pass
            async def upsert_batch(self, points): pass
            async def search_dense(self, vector, limit, filters=None): return []
            async def search_sparse(self, vector, limit, filters=None): return []
            async def delete(self, id): pass

        with pytest.raises(TypeError):
            MissingExists()