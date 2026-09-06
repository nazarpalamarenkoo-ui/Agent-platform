from FlagEmbedding import FlagReranker
from src.rag.storage.base_vector_store import VectorSearchResult


class Reranker:

    def __init__(self, top_n: int = 5):
        self.model = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=True)
        self.top_n = top_n

    def rerank(
        self,
        query: str,
        results: list[VectorSearchResult],
        top_n: int | None = None,
    ) -> list[VectorSearchResult]:

        if not results:
            return []

        n = top_n if top_n is not None else self.top_n

        pairs: list[tuple[str, str]] = [
            (query, str(result.payload["text"]))
            for result in results
        ]

        raw_scores = self.model.compute_score(pairs, normalize=True)

        if isinstance(raw_scores, float):
            scores: list[float] = [raw_scores]
        elif raw_scores is None:
            scores = [0.0] * len(pairs)
        else:
            scores = [float(s) for s in raw_scores]

        reranked = sorted(
            zip(results, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        return [
            VectorSearchResult(
                id=result.id,
                score=score,
                payload=result.payload,
            )
            for result, score in reranked[:n]
        ]