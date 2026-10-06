import argparse
import asyncio
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Literal

from qdrant_client import AsyncQdrantClient

from src.config import settings
from src.rag.embeddings.bge_m3 import Embedding
from src.rag.retrieval.query_encoder import QueryEncoder
from src.rag.retrieval.dense_search import DenseSearch
from src.rag.retrieval.sparse_search import SparseSearch
from src.rag.retrieval.rrf import RRF
from src.rag.retrieval.reranker import Reranker
from src.rag.retrieval.hybrid_retrieval import HybridRetrieval
from src.rag.retrieval.agentic.orchestrator import AgenticOrchestrator
from src.rag.retrieval.agentic.planner.llm_planner import LLMPlanner
from src.rag.retrieval.agentic.evaluator.llm_evaluator import LLMEvaluator
from src.rag.retrieval.agentic.llm_client import LLMClient
from src.rag.retrieval.agentic.search.base import Searcher
from src.rag.storage.vector_store import QdrantVectorSearch
from src.rag.rag_schemas.search_filter import SearchFilter
from tests.evaluation.report import print_report, save_report, save_charts
from tests.evaluation.models import (
    RetrievalExample,
    BenchmarkResult,
    BenchmarkMeta,
    ModeResult,
    AgenticModeResult,
    DeltaResult,
    PerQueryResult,
)
from tests.evaluation import metrics

DATASET_PATH = Path(__file__).parent / "datasets" / "retrieval_gold.json"

LIMIT = 30
TOP_N = 10
K = 60

BenchmarkMode = Literal["hybrid", "agentic", "both"]


class HybridSearchAdapter:

    def __init__(
        self,
        hybrid: HybridRetrieval,
        knowledge_packs: list[str],
        limit: int = LIMIT,
        top_n: int = TOP_N,
        k: int = K,
    ):
        self._hybrid = hybrid
        self._knowledge_packs = knowledge_packs
        self._limit = limit
        self._top_n = top_n
        self._k = k

    async def search(self, query: str):
        return await self._hybrid.retrieve(
            query=query,
            limit=self._limit,
            top_n=self._top_n,
            k=self._k,
            filters=SearchFilter(knowledge_packs=self._knowledge_packs),
        )


async def build_hybrid() -> HybridRetrieval:
    client = AsyncQdrantClient(url=settings.QDRANT_URL)
    embedding = Embedding()
    reranker = Reranker()
    vector_store = await QdrantVectorSearch.create(client, settings.QDRANT_COLLECTION)

    return HybridRetrieval(
        query_encoder=QueryEncoder(embedding),
        dense_search=DenseSearch(vector_store=vector_store),
        sparse_search=SparseSearch(vector_store=vector_store),
        rrf=RRF(),
        reranker=reranker,
    )


def build_agentic(searcher: Searcher) -> AgenticOrchestrator:
    llm_client = LLMClient(api_key=settings.MODEL_API_KEY)
    planner = LLMPlanner(llm_client=llm_client)
    evaluator = LLMEvaluator(llm_client=llm_client)

    return AgenticOrchestrator(
        planner=planner,
        evaluator=evaluator,
        searcher=searcher,
    )


def load_dataset() -> list[RetrievalExample]:
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return [RetrievalExample(**item) for item in data]


def sample_dataset(
    dataset: list[RetrievalExample],
    max_queries: int | None,
    seed: int,
) -> list[RetrievalExample]:
    """Pick a random subset of the dataset, reproducible via `seed`.

    Same seed -> same subset every time, so a hybrid-only run today and
    an agentic-only run tomorrow (two separate invocations, not --mode
    both) still compare on identical queries. A local Random instance
    is used instead of seeding the global `random` module, so this
    doesn't affect any other randomness elsewhere in the process.
    """
    if not max_queries or max_queries >= len(dataset):
        return dataset

    rng = random.Random(seed)
    return rng.sample(dataset, max_queries)


async def run_hybrid(
    hybrid: HybridRetrieval,
    dataset: list[RetrievalExample],
) -> tuple[ModeResult, list[PerQueryResult]]:
    recall5, recall10, mrr_scores, ndcg10 = [], [], [], []
    per_query: list[PerQueryResult] = []

    n = len(dataset)
    for i, example in enumerate(dataset, start=1):
        print(f"[hybrid] {i}/{n}: {example.query[:60]}")

        results = await hybrid.retrieve(
            query=example.query,
            limit=LIMIT,
            top_n=TOP_N,
            k=K,
            filters=SearchFilter(knowledge_packs=example.knowledge_packs),
        )

        retrieved_ids = [r.id for r in results]
        relevant = set(example.relevant_chunk_ids)

        r10 = metrics.recall_at_k(relevant, retrieved_ids, k=10)
        r5 = metrics.recall_at_k(relevant, retrieved_ids, k=5)
        mrr_score = metrics.mrr(relevant, retrieved_ids)
        ndcg = metrics.ndcg_at_k(relevant, retrieved_ids, k=10)

        recall5.append(r5)
        recall10.append(r10)
        mrr_scores.append(mrr_score)
        ndcg10.append(ndcg)

        per_query.append(PerQueryResult(
            id=example.id,
            query=example.query,
            relevant_count=len(relevant),
            hybrid_recall_at_10=r10,
            hybrid_mrr=mrr_score,
            hybrid_ndcg_at_10=ndcg,
        ))

    return (
        ModeResult(
            recall_at_5=sum(recall5) / n,
            recall_at_10=sum(recall10) / n,
            mrr=sum(mrr_scores) / n,
            ndcg_at_10=sum(ndcg10) / n,
        ),
        per_query,
    )


async def run_agentic(
    hybrid: HybridRetrieval,
    dataset: list[RetrievalExample],
    existing_per_query: list[PerQueryResult] | None = None,
) -> tuple[AgenticModeResult, list[PerQueryResult]]:

    recall5, recall10, mrr_scores, ndcg10 = [], [], [], []
    iterations_list: list[int] = []
    degraded_list: list[bool] = []
    coverage_list: list[float] = []
    confidence_list: list[float] = []

    pq_index: dict[str, PerQueryResult] = {}
    if existing_per_query:
        pq_index = {pq.id: pq for pq in existing_per_query}

    per_query_new: list[PerQueryResult] = []
    debug_dump: list[dict] = []

    n = len(dataset)
    for i, example in enumerate(dataset, start=1):
        print(f"[agentic] {i}/{n}: {example.query[:60]}")

        searcher = HybridSearchAdapter(
            hybrid=hybrid,
            knowledge_packs=example.knowledge_packs,
        )
        orchestrator = build_agentic(searcher)

        response = await orchestrator.retrieve(
            query=example.query,
            knowledge_packs=example.knowledge_packs,
        )

        n_iters = len(response.iterations)
        degraded = n_iters == 0
        print(f"  -> iterations={n_iters}, degraded_to_hybrid={degraded}")

        retrieved_ids = [e.chunk_id for e in response.evidence]
        direct = await hybrid.retrieve(
        query=example.query, limit=LIMIT, top_n=TOP_N, k=K,
        filters=SearchFilter(knowledge_packs=example.knowledge_packs),
        )
        direct_ids = [str(r.id) for r in direct]
        overlap = len(set(retrieved_ids[:10]) & set(direct_ids[:10]))
        print(f"  -> subqueries={len(response.plan.subqueries)}, "
            f"top10_identical={retrieved_ids[:10] == direct_ids[:10]}, overlap={overlap}/10")
        relevant = set(example.relevant_chunk_ids)

        r10 = metrics.recall_at_k(relevant, retrieved_ids, k=10)
        r5 = metrics.recall_at_k(relevant, retrieved_ids, k=5)
        mrr_score = metrics.mrr(relevant, retrieved_ids)
        ndcg = metrics.ndcg_at_k(relevant, retrieved_ids, k=10)

        recall5.append(r5)
        recall10.append(r10)
        mrr_scores.append(mrr_score)
        ndcg10.append(ndcg)

        # Only dump full iteration detail for queries where agentic
        # actually regressed vs hybrid ON THIS SAME QUERY - on ANY of
        # recall/mrr/ndcg, not just recall. Recall alone misses the
        # common case: the right chunk is found (recall unchanged) but
        # ranked lower (mrr/ndcg worse) - that's a ranking regression,
        # not a retrieval miss, and recall-only comparison hides it
        # completely.
        existing_pq = next(
            (pq for pq in (existing_per_query or []) if pq.id == example.id),
            None,
        )
        if existing_pq is not None:
            regressed = (
                (existing_pq.hybrid_recall_at_10 is not None and r10 < existing_pq.hybrid_recall_at_10)
                or (existing_pq.hybrid_mrr is not None and mrr_score < existing_pq.hybrid_mrr - 1e-9)
                or (existing_pq.hybrid_ndcg_at_10 is not None and ndcg < existing_pq.hybrid_ndcg_at_10 - 1e-9)
            )
            if regressed:
                debug_dump.append({
                    "id": example.id,
                    "query": example.query,
                    "hybrid": {
                        "recall_at_10": existing_pq.hybrid_recall_at_10,
                        "mrr": existing_pq.hybrid_mrr,
                        "ndcg_at_10": existing_pq.hybrid_ndcg_at_10,
                    },
                    "agentic": {
                        "recall_at_10": r10,
                        "mrr": mrr_score,
                        "ndcg_at_10": ndcg,
                    },
                    "initial_plan": {
                        "subqueries": response.plan.subqueries,
                        "reasoning": response.plan.reasoning,
                    },
                    "iterations": [
                        {
                            "iteration": rec.iteration,
                            "subqueries": rec.subqueries,
                            "new_evidence_count": rec.new_evidence_count,
                            "total_evidence_count": rec.total_evidence_count,
                            "evaluation": rec.evaluation.model_dump(),
                        }
                        for rec in response.iterations
                    ],
                    "final_evidence_chunk_ids_ranked": retrieved_ids,
                    "relevant_chunk_ids": list(relevant),
                })

        last_eval = response.iterations[-1].evaluation if response.iterations else None
        cov = last_eval.coverage if last_eval else 0.0
        conf = last_eval.confidence if last_eval else 0.0

        iterations_list.append(n_iters)
        degraded_list.append(degraded)
        coverage_list.append(cov)
        confidence_list.append(conf)

        if example.id in pq_index:
            pq_index[example.id].agentic_recall_at_10 = r10
            pq_index[example.id].agentic_mrr = mrr_score
            pq_index[example.id].agentic_ndcg_at_10 = ndcg
            pq_index[example.id].agentic_iterations = n_iters
            pq_index[example.id].agentic_degraded = degraded
        else:
            per_query_new.append(PerQueryResult(
                id=example.id,
                query=example.query,
                relevant_count=len(relevant),
                agentic_recall_at_10=r10,
                agentic_mrr=mrr_score,
                agentic_ndcg_at_10=ndcg,
                agentic_iterations=n_iters,
                agentic_degraded=degraded,
            ))

    result_mode = AgenticModeResult(
        recall_at_5=sum(recall5) / n,
        recall_at_10=sum(recall10) / n,
        mrr=sum(mrr_scores) / n,
        ndcg_at_10=sum(ndcg10) / n,
        avg_iterations=sum(iterations_list) / n,
        degraded_to_hybrid_pct=sum(degraded_list) / n,
        avg_coverage=sum(coverage_list) / n,
        avg_confidence=sum(confidence_list) / n,
    )

    final_per_query = existing_per_query if existing_per_query else per_query_new

    if debug_dump:
        debug_path = (
            Path(__file__).parent / "reports" /
            f"agentic_failures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(
            json.dumps(debug_dump, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n{len(debug_dump)} quer{'y' if len(debug_dump) == 1 else 'ies'} where "
              f"agentic underperformed hybrid - full iteration detail saved to:\n  {debug_path}")

    return result_mode, final_per_query


async def main(
    mode: BenchmarkMode,
    max_queries: int | None = None,
    seed: int = 42,
) -> None:
    dataset = load_dataset()
    dataset = sample_dataset(dataset, max_queries, seed)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config = {"limit": LIMIT, "top_n": TOP_N, "k": K}

    hybrid_result: ModeResult | None = None
    agentic_result: AgenticModeResult | None = None
    delta: DeltaResult | None = None
    per_query: list[PerQueryResult] = []

    hybrid = await build_hybrid()

    if mode in ("hybrid", "both"):
        print(f"Running hybrid benchmark ({len(dataset)} queries)...")
        hybrid_result, per_query = await run_hybrid(hybrid, dataset)

    if mode in ("agentic", "both"):
        print(f"Running agentic benchmark ({len(dataset)} queries)...")
        agentic_result, per_query = await run_agentic(
            hybrid, dataset,
            existing_per_query=per_query if mode == "both" else None,
        )

    if hybrid_result and agentic_result:
        delta = DeltaResult(
            recall_at_5=agentic_result.recall_at_5 - hybrid_result.recall_at_5,
            recall_at_10=agentic_result.recall_at_10 - hybrid_result.recall_at_10,
            mrr=agentic_result.mrr - hybrid_result.mrr,
            ndcg_at_10=agentic_result.ndcg_at_10 - hybrid_result.ndcg_at_10,
        )

    result = BenchmarkResult(
        meta=BenchmarkMeta(
            timestamp=timestamp,
            mode=mode,
            dataset_size=len(dataset),
            config=config,
        ),
        hybrid=hybrid_result,
        agentic=agentic_result,
        delta=delta,
        per_query=per_query,
    )

    print_report(result)
    json_path = save_report(result)
    chart_path = save_charts(result)
    print(f"\nReport saved : {json_path}")
    print(f"Charts saved : {chart_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrieval Benchmark")
    parser.add_argument(
        "--mode",
        choices=["hybrid", "agentic", "both"],
        default="hybrid",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help="Randomly sample N queries from the dataset (saves LLM API calls). "
             "Omit to use the full dataset.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for --max-queries sampling, so separate hybrid-only "
             "and agentic-only runs compare on the same subset. Change it to "
             "get a different random sample.",
    )

    args = parser.parse_args()
    asyncio.run(main(args.mode, args.max_queries, args.seed))