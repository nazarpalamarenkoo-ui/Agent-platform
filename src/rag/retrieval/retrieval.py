import asyncio

from src.rag.retrieval.query_encoder import QueryEncoder
from src.rag.retrieval.sparse_search import SparseSearch
from src.rag.retrieval.dense_search import DenseSearch
from src.rag.retrieval.rrf import RRF
from src.rag.retrieval.reranker import Reranker
from src.rag.storage.base_vector_store import VectorSearchResult
from src.rag.rag_schemas.search_filter import SearchFilter

class Retrieval:

    def __init__(
        self,
        query_encoder: QueryEncoder,
        sparse_search: SparseSearch,
        dense_search: DenseSearch,
        rrf: RRF,
        reranker: Reranker,
    ):
        self.query_encoder = query_encoder
        self.sparse_search = sparse_search
        self.dense_search = dense_search
        self.rrf = rrf
        self.reranker = reranker

    async def retrieve(
        self,
        query: str,
        limit: int,
        top_n: int,
        k: int = 60,
        filters: SearchFilter | None = None
    ) -> list[VectorSearchResult]:
        
        encoded_query = self.query_encoder.encode(query)
        
        dense_results, sparse_results = await asyncio.gather(
            self.dense_search.search(encoded_query.dense, limit, filters),
            self.sparse_search.search(encoded_query.sparse, limit, filters),
        )

        fused = self.rrf.fuse(dense_results, sparse_results, k)

        return self.reranker.rerank(query, fused, top_n)