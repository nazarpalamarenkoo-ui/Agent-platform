import logging
from typing import List, Optional

from src.rag.retrieval.agentic.evaluator.base import BaseEvaluator
from src.rag.retrieval.agentic.exceptions import LLMRateLimitError
from src.rag.retrieval.agentic.models import (
    AgenticContext,
    IterationRecord,
    RetrievalEvidence,
    SearchPlan,
    to_evidence,
)
from src.rag.retrieval.agentic.planner.base import BasePlanner
from src.rag.retrieval.agentic.search.base import Searcher

logger = logging.getLogger(__name__)

# One ranked result list produced by a single search: (is_original_query, evidence).
Ranking = tuple[bool, list[RetrievalEvidence]]


def _norm(query: str) -> str:
    return " ".join(query.lower().split())


class AgenticOrchestrator:
    """Plan -> search -> evaluate loop.

    Design rules that keep agentic >= plain hybrid on ranking quality:
      * The ORIGINAL query is always searched (iteration 1). In the fusion
        its ranking holds `original_share` of the total voting power (0.6 =
        60%), no matter how many subqueries exist. Subqueries can add recall
        and break ties, but several subqueries agreeing on the same chunk
        cannot out-vote the top of the plain hybrid ranking.
      * On top of that, the first `anchor_top_n` chunks of the original-query
        ranking are pinned at the head of the final list in their original
        order. RRF consensus can otherwise still push a hybrid top-1 down
        when one generic chunk shows up in every subquery.
      * Results of all searches are merged by weighted RRF and deduplicated
        by chunk_id. `context.evidence` is that merged, ranked list.
      * A query that was already searched is never searched again, and the
        loop stops when an iteration brings no new unique chunk.
    """

    def __init__(
        self,
        planner: BasePlanner,
        evaluator: BaseEvaluator,
        searcher: Searcher,
        max_iterations: int = 4,
        original_share: float = 0.6,
        anchor_top_n: int = 3,
        rrf_k: int = 60,
    ):
        self.planner = planner
        self.evaluator = evaluator
        self.searcher = searcher
        self.max_iterations = max_iterations
        if not 0.0 < original_share < 1.0:
            raise ValueError("original_share must be in (0, 1)")
        self.original_share = original_share
        self.anchor_top_n = anchor_top_n
        self.rrf_k = rrf_k

    async def retrieve(self, query: str, knowledge_packs: list[str]) -> AgenticContext:
        try:
            plan = await self.planner.create(query, knowledge_packs)
        except LLMRateLimitError as e:
            logger.warning(f"Planner hit rate limit, degrading to hybrid: {e}")
            return await self._fallback_to_hybrid(query)

        context = AgenticContext(
            original_query=query,
            plan=plan,
            evidence=[],
            raw_evidence=[],
            evaluation=None,
            iteration=1,
            iterations=[],
        )

        rankings: list[Ranking] = []
        searched: set[str] = set()

        subqueries = [query] + list(plan.subqueries)

        while True:
            fresh = self._fresh_queries(subqueries, searched)

            raw_hits = await self._search_subqueries(
                fresh, query, rankings, searched
            )
            context.raw_evidence.extend(raw_hits)

            known_before = {ev.chunk_id for ev in context.evidence}
            context.evidence = self._fuse(rankings)
            new_unique = sum(
                1 for ev in context.evidence if ev.chunk_id not in known_before
            )

            try:
                evaluation = await self.evaluator.evaluate(query, context.evidence)
            except LLMRateLimitError as e:
                logger.warning(
                    f"Evaluator hit rate limit at iteration {context.iteration}, "
                    f"degrading to hybrid: {e}"
                )
                return await self._fallback_to_hybrid(
                    query, rankings=rankings, searched=searched,
                    raw_evidence=context.raw_evidence,
                )

            context.evaluation = evaluation
            context.iterations.append(
                IterationRecord(
                    iteration=context.iteration,
                    subqueries=fresh,
                    new_evidence_count=len(raw_hits),
                    total_evidence_count=len(context.raw_evidence),
                    new_unique_count=new_unique,
                    total_unique_count=len(context.evidence),
                    evaluation=evaluation,
                )
            )

            logger.info(
                f"Iteration {context.iteration}/{self.max_iterations}: "
                f"sufficient={evaluation.sufficient}, coverage={evaluation.coverage:.2f}, "
                f"confidence={evaluation.confidence:.2f}, new_unique={new_unique}, "
                f"retry_queries={evaluation.retry_queries}"
            )

            if evaluation.sufficient:
                break
            if context.iteration >= self.max_iterations:
                break
            if context.iteration > 1 and new_unique == 0:
                logger.info("Stopping: last iteration found no new unique chunks")
                break

            subqueries = self._fresh_queries(evaluation.retry_queries, searched)
            if not subqueries:
                logger.info("Stopping: no new retry queries to search")
                break

            context.iteration += 1

        return context

    @staticmethod
    def _fresh_queries(queries: List[str], searched: set[str]) -> list[str]:
        """Drop queries that were already searched (or repeat inside the list)."""
        fresh: list[str] = []
        seen = set(searched)
        for q in queries:
            key = _norm(q)
            if key and key not in seen:
                seen.add(key)
                fresh.append(q)
        return fresh

    async def _search_subqueries(
        self,
        subqueries: List[str],
        original_query: str,
        rankings: list[Ranking],
        searched: set[str],
    ) -> List[RetrievalEvidence]:
        raw_hits: List[RetrievalEvidence] = []
        original_key = _norm(original_query)

        for subquery in subqueries:
            results = await self.searcher.search(subquery)
            hits = [to_evidence(subquery, result) for result in results]

            rankings.append((_norm(subquery) == original_key, hits))
            searched.add(_norm(subquery))
            raw_hits.extend(hits)

        return raw_hits

    def _fuse(self, rankings: list[Ranking]) -> list[RetrievalEvidence]:
        """Weighted Reciprocal Rank Fusion over all searches, deduped by chunk_id.

        Every subquery list has weight 1; the original-query list gets
        weight `share / (1 - share) * n_subquery_lists`, i.e. it always holds
        `original_share` of the total weight. `score` of the returned items
        is the fused score; the best raw reranker score is kept in
        `raw_score`. Ties keep first-seen order (original query is searched
        first, so it wins ties).
        """
        n_sub = sum(1 for is_orig, _ in rankings if not is_orig)
        original_weight = (
            self.original_share / (1.0 - self.original_share) * n_sub
            if n_sub else 1.0
        )

        fused: dict[str, float] = {}
        best: dict[str, RetrievalEvidence] = {}
        order: list[str] = []

        for is_orig, hits in rankings:
            weight = original_weight if is_orig else 1.0
            seen_in_list: set[str] = set()
            rank = 0
            for ev in hits:
                if ev.chunk_id in seen_in_list:
                    continue
                seen_in_list.add(ev.chunk_id)
                rank += 1

                fused[ev.chunk_id] = fused.get(ev.chunk_id, 0.0) + weight / (self.rrf_k + rank)

                current = best.get(ev.chunk_id)
                if current is None:
                    best[ev.chunk_id] = ev
                    order.append(ev.chunk_id)
                elif ev.score > current.score:
                    best[ev.chunk_id] = ev

        anchors: list[str] = []
        original_hits = next((hits for is_orig, hits in rankings if is_orig), [])
        for ev in original_hits:
            if len(anchors) >= self.anchor_top_n:
                break
            if ev.chunk_id not in anchors:
                anchors.append(ev.chunk_id)

        anchor_set = set(anchors)
        rest = sorted(
            (cid for cid in order if cid not in anchor_set),
            key=lambda cid: fused[cid],
            reverse=True,
        )
        ranked_ids = anchors + rest

        return [
            best[cid].model_copy(
                update={"score": fused[cid], "raw_score": best[cid].score}
            )
            for cid in ranked_ids
        ]

    async def _fallback_to_hybrid(
        self,
        query: str,
        rankings: Optional[list[Ranking]] = None,
        searched: Optional[set[str]] = None,
        raw_evidence: Optional[List[RetrievalEvidence]] = None,
    ) -> AgenticContext:
        rankings = list(rankings or [])
        searched = set(searched or set())
        raw = list(raw_evidence or [])

        if _norm(query) not in searched:
            results = await self.searcher.search(query)
            hits = [to_evidence(query, result) for result in results]
            rankings.append((True, hits))
            raw.extend(hits)

        return AgenticContext(
            original_query=query,
            plan=SearchPlan(subqueries=[query]),
            evidence=self._fuse(rankings),
            raw_evidence=raw,
            evaluation=None,
            iteration=1,
            iterations=[],
        )