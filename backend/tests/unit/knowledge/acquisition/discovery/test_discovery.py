from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.knowledge.acquisition.discovery.discovery import Discovery
from src.knowledge.acquisition.discovery.result_parser import ResultParser
from src.knowledge.acquisition.search import SearXNG, SearXNGUnavailableError
from src.knowledge.documents_schema.discovery_model import DiscoveryResult
from src.knowledge.documents_schema.search_schema import SearchResult


def sr(url, title="t"):
    return SearchResult(url=url, title=title, snippet="s", source="searxng")


@pytest.fixture
def search_engine():
    return MagicMock(spec=SearXNG)


@pytest.fixture
def discovery(search_engine):
    return Discovery(search_engine=search_engine, parser=ResultParser(), max_results_per_query=5)


class TestSearchOne:

    @pytest.mark.asyncio
    async def test_parses_results(self, discovery, search_engine):
        search_engine.search = AsyncMock(return_value=[sr("https://a.com/x")])

        results = await discovery._search_one("q")

        assert len(results) == 1
        assert isinstance(results[0], DiscoveryResult)
        assert results[0].domain == "a.com"

    @pytest.mark.asyncio
    async def test_passes_limit_to_search_engine(self, discovery, search_engine):
        search_engine.search = AsyncMock(return_value=[])

        await discovery._search_one("q")

        search_engine.search.assert_awaited_once_with("q", limit=5)

    @pytest.mark.asyncio
    async def test_unavailable_engine_returns_empty_list(self, discovery, search_engine):
        search_engine.search = AsyncMock(side_effect=SearXNGUnavailableError("down"))

        assert await discovery._search_one("q") == []


class TestDeduplicateByUrl:

    def test_removes_trailing_slash_and_case_duplicates(self, discovery):
        parsed = ResultParser().parse_many([sr("https://a.com/X"), sr("https://a.com/x/"), sr("https://b.com")])

        unique = discovery._deduplicate_by_url(parsed)

        assert [r.url for r in unique] == ["https://a.com/X", "https://b.com"]

    def test_keeps_first_occurrence(self, discovery):
        parsed = ResultParser().parse_many([sr("https://a.com", "first"), sr("https://a.com/", "second")])

        assert discovery._deduplicate_by_url(parsed)[0].title == "first"


class TestSearchMany:

    @pytest.mark.asyncio
    async def test_empty_strategies_returns_empty_without_search(self, discovery, search_engine):
        search_engine.search = AsyncMock()

        assert await discovery.search_many([]) == []
        search_engine.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_searches_every_strategy(self, discovery, search_engine):
        search_engine.search = AsyncMock(return_value=[])

        await discovery.search_many(["q1", "q2", "q3"])

        assert search_engine.search.await_count == 3
        queried = {call.args[0] for call in search_engine.search.await_args_list}
        assert queried == {"q1", "q2", "q3"}

    @pytest.mark.asyncio
    async def test_merges_and_deduplicates_across_strategies(self, discovery, search_engine):
        responses = {
            "q1": [sr("https://a.com"), sr("https://b.com")],
            "q2": [sr("https://b.com/"), sr("https://c.com")],
        }
        search_engine.search = AsyncMock(side_effect=lambda q, limit: responses[q])

        results = await discovery.search_many(["q1", "q2"])

        assert [r.url for r in results] == ["https://a.com", "https://b.com", "https://c.com"]

    @pytest.mark.asyncio
    async def test_one_unavailable_strategy_does_not_break_others(self, discovery, search_engine):
        async def side_effect(q, limit):
            if q == "bad":
                raise SearXNGUnavailableError("down")
            return [sr("https://ok.com")]

        search_engine.search = AsyncMock(side_effect=side_effect)

        results = await discovery.search_many(["bad", "good"])

        assert [r.url for r in results] == ["https://ok.com"]

    @pytest.mark.asyncio
    async def test_other_errors_propagate(self, discovery, search_engine):
        search_engine.search = AsyncMock(side_effect=httpx.HTTPError("400"))

        with pytest.raises(httpx.HTTPError):
            await discovery.search_many(["q"])