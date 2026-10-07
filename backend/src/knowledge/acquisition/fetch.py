import asyncio
import hashlib
import mimetypes
from datetime import datetime, timezone

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.knowledge.documents_schema.raw_document import RawDocument

BLOCKED_STATUS_CODES = {401, 403, 405, 451}

RETRYABLE_STATUS_CODES = {429, 503}


class FetcherUnavailableError(Exception):
    ""
class FetcherBlockedError(Exception):
    ""
class Fetcher:

    def __init__(
        self,
        client: httpx.AsyncClient,
        timeout: float = 10.0,
        max_concurrency: int = 5,
    ):
        self.client = client
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def fetch(self, url: str) -> RawDocument:
        async with self._semaphore:
            return await self._fetch_with_retry(url)

    @retry(
        retry=retry_if_exception_type(FetcherUnavailableError),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _fetch_with_retry(self, url: str) -> RawDocument:
        try:
            response = await self.client.get(url, timeout=self.timeout)
        except httpx.ConnectError as e:
            raise FetcherUnavailableError(f"Cannot connect to {url}: {e}") from e
        except httpx.TimeoutException as e:
            raise FetcherUnavailableError(f"Timeout fetching {url}: {e}") from e

        status = response.status_code

        if status in RETRYABLE_STATUS_CODES:
            raise FetcherUnavailableError(f"HTTP {status} for {url}")
        if status in BLOCKED_STATUS_CODES:
            raise FetcherBlockedError(f"Blocked by site (HTTP {status}) for {url}")
        if status >= 400:
            raise httpx.HTTPError(f"HTTP {status} for {url}")

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()

        if not content_type or content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(url)
            content_type = guessed or "text/html"

        return RawDocument(
            source=url,
            content=response.content,
            content_type=content_type,
            content_hash=hashlib.sha256(response.content).hexdigest(),
            fetched_at=datetime.now(timezone.utc),
        )