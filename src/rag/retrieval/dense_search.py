from src.rag.embeddings.bge_m3 import Embedding
from src.rag.storage.base_vector_store import BaseVectorStorage, VectorSearchResult

class DenseSearch:
    
    def __init__(self, embedding: Embedding, vector_store: BaseVectorStorage):
        
        self.embedding = embedding
        self.vector_store = vector_store
        
    async def search(self, query: str, limit: int) -> list[VectorSearchResult]:
        
        embedding_result = self.embedding.embed([query])[0]
        return await self.vector_store.search_dense(
            vector=embedding_result.dense,
            limit=limit,
        )