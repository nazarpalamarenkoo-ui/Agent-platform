import asyncio
import logging

from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.acquisition.judge.models import DocumentDecision
from src.knowledge.acquisition.search import SearXNG
from src.knowledge.acquisition.fetch import Fetcher
from src.knowledge.acquisition.discovery.query_builder import QueryBuilder
from src.knowledge.acquisition.discovery.discovery import Discovery
from src.knowledge.acquisition.dedup.deduplicator import Deduplicator
from src.knowledge.acquisition.ranking.ranker import Ranker
from src.knowledge.acquisition.preview_fetcher.preview_fetrcher import PreviewFetcher
from src.knowledge.acquisition.judge.llm_judge import LLMJudge
from src.knowledge.acquisition.judge.decision_engine import DecisionEngine
from src.knowledge.acquisition.judge.judge_persistence import JudgePersistence

logger = logging.getLogger(__name__)


class Orchestrator:

    def __init__(
        self,
        fetcher: Fetcher,
        query_builder: QueryBuilder,
        discovery: Discovery,
        deduplicator: Deduplicator,
        ranker: Ranker,
        preview_fetcher: PreviewFetcher,
        llm_judge: LLMJudge,
        decision_engine: DecisionEngine,
        judge_persistence: JudgePersistence,
    ):
        self.fetcher = fetcher
        self.query_builder = query_builder
        self.discovery = discovery
        self.deduplicator = deduplicator
        self.ranker = ranker
        self.preview_fetcher = preview_fetcher
        self.llm_judge = llm_judge
        self.decision_engine = decision_engine
        self.judge_persistence = judge_persistence

    async def orchestrate(self, query: str) -> list[RawDocument]:
        strategies = self.query_builder.build(query)
        logger.info("[%s] strategies=%d", query, len(strategies))

        candidates = await self.discovery.search_many(strategies)
        logger.info("[%s] discovery=%d", query, len(candidates))

        unique = await self.deduplicator.remove_duplicates(candidates)
        logger.info("[%s] dedup=%d (removed %d)", query, len(unique), len(candidates) - len(unique))

        ranked = self.ranker.rank(query, unique)
        logger.info("[%s] ranked=%d", query, len(ranked))

        previews = await self.preview_fetcher.fetch_many(ranked, query)
        logger.info("[%s] previews=%d (failed %d)", query, len(previews), len(ranked) - len(previews))

        judge = await self.llm_judge.evaluate(previews)
        decided = self.decision_engine.decide_many(judge)

        accepted = [d for d in decided if d.decision == DocumentDecision.ACCEPT]
        judge_errors = sum(1 for d in decided if d.source.document_category == "judge_error")
        logger.info(
            "[%s] judge: accepted=%d rejected=%d judge_errors=%d",
            query, len(accepted), len(decided) - len(accepted) - judge_errors, judge_errors,
        )

        await self.judge_persistence.save(decided)

        fetch_tasks = [self.fetcher.fetch(d.source.url) for d in accepted]
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        raw_docs = []
        for decision_source, result in zip(accepted, results):
            if isinstance(result, Exception):
                logger.warning("Full fetch failed for %s: %s", decision_source.source.url, result)
                continue
            raw_docs.append(result)

        logger.info("[%s] final raw_docs=%d", query, len(raw_docs))
        return raw_docs