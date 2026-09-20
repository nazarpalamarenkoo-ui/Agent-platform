from src.rag.rag_schemas.search_filter import SearchFilter
from src.rag.storage.base_vector_store import BaseVectorStorage, VectorSearchResult, DenseVector

class DenseSearch:
    
    def __init__(self, vector_store: BaseVectorStorage):
        self.vector_store = vector_store
        
    async def search(self, vector: DenseVector, limit: int, filters: SearchFilter | None = None) -> list[VectorSearchResult]:
        return await self.vector_store.search_dense(
            vector=vector,
            limit=limit,
            filters=filters
        )