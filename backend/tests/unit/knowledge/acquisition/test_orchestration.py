import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.knowledge.acquisition.dedup.deduplicator import Deduplicator
from src.knowledge.acquisition.discovery.discovery import Discovery
from src.knowledge.acquisition.discovery.query_builder import QueryBuilder
from src.knowledge.acquisition.fetch import Fetcher
from src.knowledge.acquisition.judge.decision_engine import DecisionEngine
from src.knowledge.acquisition.judge.judge_persistence import JudgePersistence
from src.knowledge.acquisition.judge.llm_judge import LLMJudge
from src.knowledge.acquisition.judge.models import (
    DecidedSource,
    DocumentDecision,
    JudgeSource,
    TrustBreakdown,
)
from src.knowledge.acquisition.orchestration import Orchestrator
from src.knowledge.acquisition.preview_fetcher.preview_fetrcher import PreviewFetcher
from src.knowledge.acquisition.ranking.ranker import Ranker
from src.knowledge.documents_schema.raw_document import RawDocument

from datetime import datetime, timezone
import hashlib


def make_raw_document(source="https://example.com", content=b"content"):
    return RawDocument(
        source=source,
        content=content,
        content_type="text/html",
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at=datetime.now(timezone.utc),
    )


def make_decided(url, decision=DocumentDecision.ACCEPT, score=0.9):
    source = JudgeSource(
        key=f"key-{url}",
        url=url,
        title="t",
        trust=TrustBreakdown(educational=0.9, implementation=0.9, authority=0.9),
        document_category="tutorial",
        reason="r",
    )
    return DecidedSource(source=source, decision=decision, overall_score=score)


@pytest.fixture
def deps():
    d = type("Deps", (), {})()
    d.fetcher = MagicMock(spec=Fetcher)
    d.fetcher.fetch = AsyncMock(side_effect=lambda url: make_raw_document(url))

    d.query_builder = MagicMock(spec=QueryBuilder)
    d.query_builder.build.return_value = ["q pdf", "q whitepaper"]

    d.discovery = MagicMock(spec=Discovery)
    d.discovery.search_many = AsyncMock(return_value=["candidate"])

    d.deduplicator = MagicMock(spec=Deduplicator)
    d.deduplicator.remove_duplicates = AsyncMock(return_value=["unique"])

    d.ranker = MagicMock(spec=Ranker)
    d.ranker.rank.return_value = ["ranked"]

    d.preview_fetcher = MagicMock(spec=PreviewFetcher)
    d.preview_fetcher.fetch_many = AsyncMock(return_value=["preview"])

    d.llm_judge = MagicMock(spec=LLMJudge)
    d.llm_judge.evaluate = AsyncMock(return_value=["judged"])

    d.decision_engine = MagicMock(spec=DecisionEngine)
    d.decision_engine.decide_many.return_value = [make_decided("https://a.com")]

    d.judge_persistence = MagicMock(spec=JudgePersistence)
    d.judge_persistence.save = AsyncMock()
    return d


@pytest.fixture
def orchestrator(deps):
    return Orchestrator(
        fetcher=deps.fetcher,
        query_builder=deps.query_builder,
        discovery=deps.discovery,
        deduplicator=deps.deduplicator,
        ranker=deps.ranker,
        preview_fetcher=deps.preview_fetcher,
        llm_judge=deps.llm_judge,
        decision_engine=deps.decision_engine,
        judge_persistence=deps.judge_persistence,
    )


class TestPipelineWiring:

    @pytest.mark.asyncio
    async def test_passes_data_between_stages(self, orchestrator, deps):
        await orchestrator.orchestrate("my query")

        deps.query_builder.build.assert_called_once_with("my query")
        deps.discovery.search_many.assert_awaited_once_with(["q pdf", "q whitepaper"])
        deps.deduplicator.remove_duplicates.assert_awaited_once_with(["candidate"])
        deps.ranker.rank.assert_called_once_with("my query", ["unique"])
        deps.preview_fetcher.fetch_many.assert_awaited_once_with(["ranked"], "my query")
        deps.llm_judge.evaluate.assert_awaited_once_with(["preview"])
        deps.decision_engine.decide_many.assert_called_once_with(["judged"])

    @pytest.mark.asyncio
    async def test_query_builder_error_propagates(self, orchestrator, deps):
        deps.query_builder.build.side_effect = ValueError("Query cannot be empty")

        with pytest.raises(ValueError):
            await orchestrator.orchestrate("")

        deps.discovery.search_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_stages_empty_returns_empty_list(self, orchestrator, deps):
        deps.discovery.search_many = AsyncMock(return_value=[])
        deps.deduplicator.remove_duplicates = AsyncMock(return_value=[])
        deps.ranker.rank.return_value = []
        deps.preview_fetcher.fetch_many = AsyncMock(return_value=[])
        deps.llm_judge.evaluate = AsyncMock(return_value=[])
        deps.decision_engine.decide_many.return_value = []

        assert await orchestrator.orchestrate("q") == []
        deps.fetcher.fetch.assert_not_called()


class TestAcceptedFetch:

    @pytest.mark.asyncio
    async def test_fetches_only_accepted_documents(self, orchestrator, deps):
        deps.decision_engine.decide_many.return_value = [
            make_decided("https://a.com", DocumentDecision.ACCEPT),
            make_decided("https://b.com", DocumentDecision.REJECT, 0.2),
            make_decided("https://c.com", DocumentDecision.ACCEPT),
        ]

        results = await orchestrator.orchestrate("q")

        fetched = {c.args[0] for c in deps.fetcher.fetch.await_args_list}
        assert fetched == {"https://a.com", "https://c.com"}
        assert {r.source for r in results} == {"https://a.com", "https://c.com"}

    @pytest.mark.asyncio
    async def test_no_accepted_returns_empty_and_skips_fetch(self, orchestrator, deps):
        deps.decision_engine.decide_many.return_value = [
            make_decided("https://b.com", DocumentDecision.REJECT, 0.2)
        ]

        assert await orchestrator.orchestrate("q") == []
        deps.fetcher.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_full_fetch_is_excluded(self, orchestrator, deps):
        deps.decision_engine.decide_many.return_value = [
            make_decided("https://ok.com"),
            make_decided("https://fails.com"),
        ]

        async def fetch(url):
            if "fails" in url:
                raise ConnectionError("down")
            return make_raw_document(url)

        deps.fetcher.fetch = AsyncMock(side_effect=fetch)

        results = await orchestrator.orchestrate("q")

        assert [r.source for r in results] == ["https://ok.com"]

    @pytest.mark.asyncio
    async def test_all_full_fetches_failing_returns_empty(self, orchestrator, deps):
        deps.fetcher.fetch = AsyncMock(side_effect=ConnectionError("down"))

        assert await orchestrator.orchestrate("q") == []

    @pytest.mark.asyncio
    async def test_preserves_order_of_accepted_documents(self, orchestrator, deps):
        urls = [f"https://s{i}.com" for i in range(4)]
        deps.decision_engine.decide_many.return_value = [make_decided(u) for u in urls]

        results = await orchestrator.orchestrate("q")

        assert [r.source for r in results] == urls

    @pytest.mark.asyncio
    async def test_full_fetches_run_concurrently(self, orchestrator, deps):
        urls = [f"https://s{i}.com" for i in range(3)]
        deps.decision_engine.decide_many.return_value = [make_decided(u) for u in urls]

        async def slow_fetch(url):
            await asyncio.sleep(0.05)
            return make_raw_document(url)

        deps.fetcher.fetch = AsyncMock(side_effect=slow_fetch)

        start = asyncio.get_event_loop().time()
        results = await orchestrator.orchestrate("q")
        elapsed = asyncio.get_event_loop().time() - start

        assert len(results) == 3
        assert elapsed < 0.12


class TestPersistence:

    @pytest.mark.asyncio
    async def test_saves_all_decisions_including_rejected(self, orchestrator, deps):
        decided = [
            make_decided("https://a.com", DocumentDecision.ACCEPT),
            make_decided("https://b.com", DocumentDecision.REJECT, 0.1),
        ]
        deps.decision_engine.decide_many.return_value = decided

        await orchestrator.orchestrate("q")

        deps.judge_persistence.save.assert_awaited_once_with(decided)

    @pytest.mark.asyncio
    async def test_persistence_happens_before_full_fetch(self, orchestrator, deps):
        calls = []
        deps.judge_persistence.save = AsyncMock(side_effect=lambda d: calls.append("save"))
        deps.fetcher.fetch = AsyncMock(
            side_effect=lambda url: calls.append("fetch") or make_raw_document(url)
        )

        await orchestrator.orchestrate("q")

        assert calls == ["save", "fetch"]

    @pytest.mark.asyncio
    async def test_persistence_error_propagates_and_stops_fetch(self, orchestrator, deps):
        deps.judge_persistence.save = AsyncMock(side_effect=RuntimeError("db down"))

        with pytest.raises(RuntimeError):
            await orchestrator.orchestrate("q")

        deps.fetcher.fetch.assert_not_called()