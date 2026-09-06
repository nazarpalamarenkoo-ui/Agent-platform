from collections import defaultdict
from src.rag.storage.base_vector_store import VectorSearchResult

class RRF:

    def fuse(
        self,
        dense_results: list[VectorSearchResult],
        sparce_results: list[VectorSearchResult],
        k: int = 60
    ) -> list[VectorSearchResult]:
        
        scores: dict[str, float] = defaultdict(float)
        docs: dict[str, VectorSearchResult] = {}
        
        for rank, result in enumerate(dense_results):
            scores[result.id] += 1 / (k + rank)
            docs[result.id] = result
            
        for rank, result in enumerate(sparce_results):
            scores[result.id] += 1 / (k + rank)
            docs[result.id] = result
            
        sorted_ids = sorted(scores, key = lambda id: scores[id], reverse=True)
        
        return [
            VectorSearchResult(
                id=doc_id,
                score=scores[doc_id],
                payload=docs[doc_id].payload,
            )
            for doc_id in sorted_ids
        ]