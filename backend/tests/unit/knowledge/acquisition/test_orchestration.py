import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.knowledge.acquisition.orchestration import Orchestrator
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.documents_schema.search_schema import SearchResult


def make_search_result(url="https://example.com"):
    return SearchResult(url=url, title="title", snippet="snippet")


def make_raw_document(source="https://example.com", content=b"content"):
    return RawDocument(
        source=source,
        content=content,
        content_type="text/html",
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_search_engine():
    return MagicMock()


@pytest.fixture
def mock_fetcher():
    return MagicMock()


@pytest.fixture
def orchestrator(mock_search_engine, mock_fetcher):
    return Orchestrator(search_engine=mock_search_engine, fetcher=mock_fetcher)


class TestOrchestrate:

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_search_results(self, orchestrator, mock_search_engine, mock_fetcher):
        mock_search_engine.search = AsyncMock(return_value=[])
        mock_fetcher.fetch = AsyncMock()

        results = await orchestrator.orchestrate("query")

        assert results == []
        mock_fetcher.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_all_search_results_and_returns_raw_documents(
        self, orchestrator, mock_search_engine, mock_fetcher
    ):
        search_results = [make_search_result("https://a.com"), make_search_result("https://b.com")]
        mock_search_engine.search = AsyncMock(return_value=search_results)

        fetched_docs = {
            "https://a.com": make_raw_document("https://a.com", b"content a"),
            "https://b.com": make_raw_document("https://b.com", b"content b"),
        }
        mock_fetcher.fetch = AsyncMock(side_effect=lambda url: fetched_docs[url])

        results = await orchestrator.orchestrate("query", limit=2)

        assert len(results) == 2
        assert {r.source for r in results} == {"https://a.com", "https://b.com"}
        assert mock_fetcher.fetch.await_count == 2

    @pytest.mark.asyncio
    async def test_passes_query_and_limit_to_search_engine(self, orchestrator, mock_search_engine, mock_fetcher):
        mock_search_engine.search = AsyncMock(return_value=[])

        await orchestrator.orchestrate("my query", limit=7)

        mock_search_engine.search.assert_awaited_once_with("my query", limit=7)

    @pytest.mark.asyncio
    async def test_default_limit_is_five(self, orchestrator, mock_search_engine, mock_fetcher):
        mock_search_engine.search = AsyncMock(return_value=[])

        await orchestrator.orchestrate("query")

        mock_search_engine.search.assert_awaited_once_with("query", limit=5)

    @pytest.mark.asyncio
    async def test_recomputes_content_hash_from_fetched_content(
        self, orchestrator, mock_search_engine, mock_fetcher
    ):
        mock_search_engine.search = AsyncMock(return_value=[make_search_result("https://a.com")])
        raw = make_raw_document("https://a.com", b"real content")
        raw.content_hash = "0" * 64
        mock_fetcher.fetch = AsyncMock(return_value=raw)

        results = await orchestrator.orchestrate("query", limit=1)

        assert results[0].content_hash == hashlib.sha256(b"real content").hexdigest()

    @pytest.mark.asyncio
    async def test_fetch_exceptions_are_excluded_from_results(
        self, orchestrator, mock_search_engine, mock_fetcher
    ):
        search_results = [make_search_result("https://a.com"), make_search_result("https://fails.com")]
        mock_search_engine.search = AsyncMock(return_value=search_results)

        async def fetch_side_effect(url):
            if url == "https://fails.com":
                raise ConnectionError("network down")
            return make_raw_document(url, b"good content")

        mock_fetcher.fetch = AsyncMock(side_effect=fetch_side_effect)

        results = await orchestrator.orchestrate("query", limit=2)

        assert len(results) == 1
        assert results[0].source == "https://a.com"

    @pytest.mark.asyncio
    async def test_all_fetches_failing_returns_empty_list(self, orchestrator, mock_search_engine, mock_fetcher):
        mock_search_engine.search = AsyncMock(return_value=[make_search_result("https://a.com")])
        mock_fetcher.fetch = AsyncMock(side_effect=ConnectionError("down"))

        results = await orchestrator.orchestrate("query", limit=1)

        assert results == []

    @pytest.mark.asyncio
    async def test_fetches_run_concurrently_not_sequentially(
        self, orchestrator, mock_search_engine, mock_fetcher
    ):
        import asyncio

        search_results = [make_search_result(f"https://{i}.com") for i in range(3)]
        mock_search_engine.search = AsyncMock(return_value=search_results)

        async def slow_fetch(url):
            await asyncio.sleep(0.05)
            return make_raw_document(url, b"content")

        mock_fetcher.fetch = AsyncMock(side_effect=slow_fetch)

        start = asyncio.get_event_loop().time()
        results = await orchestrator.orchestrate("query", limit=3)
        elapsed = asyncio.get_event_loop().time() - start

        assert len(results) == 3
        assert elapsed < 0.12