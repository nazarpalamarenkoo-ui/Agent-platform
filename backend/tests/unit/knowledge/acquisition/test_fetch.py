import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.knowledge.acquisition.fetch import (
    Fetcher,
    FetcherBlockedError,
    FetcherUnavailableError,
)
from src.knowledge.documents_schema.raw_document import RawDocument

_REAL_SLEEP = asyncio.sleep


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):

    async def fast_sleep(_seconds):
        await _REAL_SLEEP(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)


def make_response(status_code=200, content=b"", headers=None):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.content = content
    response.text = content.decode(errors="ignore") if isinstance(content, bytes) else str(content)
    response.headers = headers or {}
    return response


@pytest.fixture
def mock_client():
    return MagicMock(spec=httpx.AsyncClient)


@pytest.fixture
def fetcher(mock_client):
    return Fetcher(client=mock_client)


class TestFetcherFetch:

    @pytest.mark.asyncio
    async def test_returns_raw_document_with_expected_fields(self, fetcher, mock_client):
        content = b"<html>hello</html>"
        mock_client.get = AsyncMock(return_value=make_response(
            content=content, headers={"content-type": "text/html; charset=utf-8"}
        ))

        result = await fetcher.fetch("https://example.com/page")

        assert isinstance(result, RawDocument)
        assert result.source == "https://example.com/page"
        assert result.content == content
        assert result.content_type == "text/html"
        assert result.content_hash == hashlib.sha256(content).hexdigest()
        assert result.fetched_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_content_type_is_lowercased(self, fetcher, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(
            content=b"x", headers={"content-type": "Application/PDF; charset=binary"}
        ))

        result = await fetcher.fetch("https://example.com/a")

        assert result.content_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_passes_url_and_timeout_to_client(self, fetcher, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(headers={"content-type": "text/plain"}))

        await fetcher.fetch("https://example.com/doc.txt")

        mock_client.get.assert_awaited_once_with("https://example.com/doc.txt", timeout=fetcher.timeout)

    @pytest.mark.asyncio
    async def test_missing_content_type_falls_back_to_guessed_type(self, fetcher, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(content=b"data", headers={}))

        result = await fetcher.fetch("https://example.com/report.pdf")

        assert result.content_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_octet_stream_falls_back_to_guessed_type(self, fetcher, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(
            content=b"data", headers={"content-type": "application/octet-stream"}
        ))

        result = await fetcher.fetch("https://example.com/image.png")

        assert result.content_type == "image/png"

    @pytest.mark.asyncio
    async def test_unknown_extension_defaults_to_text_html(self, fetcher, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(content=b"data", headers={}))

        result = await fetcher.fetch("https://example.com/unknownpath")

        assert result.content_type == "text/html"

    @pytest.mark.asyncio
    async def test_content_hash_is_deterministic_for_same_content(self, fetcher, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(
            content=b"same bytes", headers={"content-type": "text/plain"}
        ))

        first = await fetcher.fetch("https://example.com/a")
        second = await fetcher.fetch("https://example.com/b")

        assert first.content_hash == second.content_hash


class TestFetcherErrors:

    @pytest.mark.asyncio
    async def test_connect_error_raises_unavailable_after_retries(self, fetcher, mock_client):
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with pytest.raises(FetcherUnavailableError):
            await fetcher.fetch("https://example.com")

        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_timeout_error_raises_unavailable_after_retries(self, fetcher, mock_client):
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with pytest.raises(FetcherUnavailableError):
            await fetcher.fetch("https://example.com")

        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [429, 503])
    async def test_retryable_status_raises_unavailable_after_retries(self, fetcher, mock_client, status):
        mock_client.get = AsyncMock(return_value=make_response(status_code=status))

        with pytest.raises(FetcherUnavailableError):
            await fetcher.fetch("https://example.com")

        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_recovers_after_transient_failure(self, fetcher, mock_client):
        mock_client.get = AsyncMock(side_effect=[
            httpx.ConnectError("boom"),
            make_response(content=b"ok", headers={"content-type": "text/plain"}),
        ])

        result = await fetcher.fetch("https://example.com")

        assert result.content == b"ok"
        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [401, 403, 405, 451])
    async def test_blocked_status_raises_blocked_without_retry(self, fetcher, mock_client, status):
        mock_client.get = AsyncMock(return_value=make_response(status_code=status))

        with pytest.raises(FetcherBlockedError):
            await fetcher.fetch("https://example.com")

        assert mock_client.get.await_count == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 404, 500])
    async def test_other_error_status_raises_http_error_without_retry(self, fetcher, mock_client, status):
        mock_client.get = AsyncMock(return_value=make_response(status_code=status))

        with pytest.raises(httpx.HTTPError):
            await fetcher.fetch("https://example.com")

        assert mock_client.get.await_count == 1


class TestFetcherConcurrency:

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_requests(self, mock_client):
        fetcher = Fetcher(client=mock_client, max_concurrency=2)
        current = 0
        peak = 0

        async def slow_get(url, timeout):
            nonlocal current, peak
            current += 1
            peak = max(peak, current)
            await _REAL_SLEEP(0.01)
            current -= 1
            return make_response(content=b"x", headers={"content-type": "text/plain"})

        mock_client.get = AsyncMock(side_effect=slow_get)

        results = await asyncio.gather(*[fetcher.fetch(f"https://e.com/{i}") for i in range(6)])

        assert len(results) == 6
        assert peak == 2