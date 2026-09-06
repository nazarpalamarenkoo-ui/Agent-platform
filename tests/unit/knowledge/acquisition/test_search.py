import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.knowledge.acquisition.search import SearXNG, SearXNGUnavailableError
from src.knowledge.documents_schema.search_schema import SearchResult


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    async def instant_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", instant_sleep)


def make_response(status_code=200, json_data=None, text=""):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.text = text
    return response


@pytest.fixture
def mock_client():
    return MagicMock(spec=httpx.AsyncClient)


@pytest.fixture
def searxng(mock_client):
    return SearXNG(base_url="http://searxng.local/", client=mock_client)


class TestSearXNGInit:

    def test_strips_trailing_slash_from_base_url(self, mock_client):
        engine = SearXNG(base_url="http://searxng.local/", client=mock_client)
        assert engine.base_url == "http://searxng.local"

    def test_default_timeout(self, mock_client):
        engine = SearXNG(base_url="http://searxng.local", client=mock_client)
        assert engine.timeout == 10.0

    def test_custom_timeout(self, mock_client):
        engine = SearXNG(base_url="http://searxng.local", client=mock_client, timeout=5.0)
        assert engine.timeout == 5.0


class TestSearXNGSearch:

    @pytest.mark.asyncio
    async def test_returns_parsed_search_results(self, searxng, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(
            status_code=200,
            json_data={
                "results": [
                    {"url": "https://a.com", "title": "A", "content": "snippet a", "score": 1.2},
                    {"url": "https://b.com", "title": "B", "content": "snippet b"},
                ]
            },
        ))

        results = await searxng.search("python testing", limit=5)

        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)
        assert results[0].url == "https://a.com"
        assert results[0].title == "A"
        assert results[0].snippet == "snippet a"
        assert results[0].score == 1.2
        assert results[0].source == "searxng"
        assert results[1].score is None

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint_and_params(self, searxng, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(json_data={"results": []}))

        await searxng.search("some query", limit=3)

        mock_client.get.assert_awaited_once()
        args, kwargs = mock_client.get.call_args
        assert args[0] == "http://searxng.local/search"
        assert kwargs["params"] == {"q": "some query", "format": "json", "categories": "general"}
        assert kwargs["timeout"] == searxng.timeout

    @pytest.mark.asyncio
    async def test_respects_limit_even_with_more_results_available(self, searxng, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(
            json_data={"results": [{"url": f"https://{i}.com", "title": str(i), "content": ""} for i in range(10)]}
        ))

        results = await searxng.search("query", limit=3)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_skips_results_missing_url(self, searxng, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(
            json_data={"results": [
                {"title": "no url", "content": "x"},
                {"url": "https://ok.com", "title": "ok", "content": "y"},
            ]}
        ))

        results = await searxng.search("query", limit=5)

        assert len(results) == 1
        assert results[0].url == "https://ok.com"

    @pytest.mark.asyncio
    async def test_no_results_key_returns_empty_list(self, searxng, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(json_data={}))

        results = await searxng.search("query", limit=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_connect_error_raises_unavailable_after_retries(self, searxng, mock_client):
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with pytest.raises(SearXNGUnavailableError):
            await searxng.search("query", limit=5)

        assert mock_client.get.await_count == 3

    @pytest.mark.asyncio
    async def test_timeout_error_raises_unavailable_after_retries(self, searxng, mock_client):
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with pytest.raises(SearXNGUnavailableError):
            await searxng.search("query", limit=5)

        assert mock_client.get.await_count == 3

    @pytest.mark.asyncio
    async def test_503_response_raises_unavailable_after_retries(self, searxng, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(status_code=503, text="down"))

        with pytest.raises(SearXNGUnavailableError):
            await searxng.search("query", limit=5)

        assert mock_client.get.await_count == 3

    @pytest.mark.asyncio
    async def test_recovers_after_transient_failure(self, searxng, mock_client):
        mock_client.get = AsyncMock(side_effect=[
            httpx.ConnectError("boom"),
            make_response(json_data={"results": [{"url": "https://a.com", "title": "A", "content": ""}]}),
        ])

        results = await searxng.search("query", limit=5)

        assert len(results) == 1
        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_400_error_raises_http_error_without_retry(self, searxng, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(status_code=404, text="not found"))

        with pytest.raises(httpx.HTTPError):
            await searxng.search("query", limit=5)

        # non-503 HTTP errors are not part of the retry condition
        assert mock_client.get.await_count == 1