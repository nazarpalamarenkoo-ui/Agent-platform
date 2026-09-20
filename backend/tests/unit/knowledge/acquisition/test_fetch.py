import hashlib
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.knowledge.acquisition.fetch import Fetcher, FetcherUnavailableError
from src.knowledge.documents_schema.raw_document import RawDocument


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
    async def test_connect_error_raises_fetcher_unavailable(self, fetcher, mock_client):
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with pytest.raises(FetcherUnavailableError):
            await fetcher.fetch("https://example.com")

    @pytest.mark.asyncio
    async def test_timeout_error_raises_fetcher_unavailable(self, fetcher, mock_client):
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with pytest.raises(FetcherUnavailableError):
            await fetcher.fetch("https://example.com")

    @pytest.mark.asyncio
    async def test_503_status_raises_fetcher_unavailable(self, fetcher, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(status_code=503, content=b"down"))

        with pytest.raises(FetcherUnavailableError):
            await fetcher.fetch("https://example.com")

    @pytest.mark.asyncio
    async def test_404_status_raises_http_error(self, fetcher, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(status_code=404, content=b"not found"))

        with pytest.raises(httpx.HTTPError):
            await fetcher.fetch("https://example.com/missing")

    @pytest.mark.asyncio
    async def test_500_status_raises_http_error(self, fetcher, mock_client):
        mock_client.get = AsyncMock(return_value=make_response(status_code=500, content=b"boom"))

        with pytest.raises(httpx.HTTPError):
            await fetcher.fetch("https://example.com/broken")

    @pytest.mark.asyncio
    async def test_content_hash_is_deterministic_for_same_content(self, fetcher, mock_client):
        content = b"same bytes"
        mock_client.get = AsyncMock(return_value=make_response(
            content=content, headers={"content-type": "text/plain"}
        ))

        first = await fetcher.fetch("https://example.com/a")
        second = await fetcher.fetch("https://example.com/b")

        assert first.content_hash == second.content_hash