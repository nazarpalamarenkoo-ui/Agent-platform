import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.knowledge.documents_schema.search_schema import SearchResult

class SearXNGUnavailableError(Exception):
    pass

class SearXNG():

    def __init__(self, base_url: str, client: httpx.AsyncClient, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.timeout = timeout

    @retry(
        retry=retry_if_exception_type(SearXNGUnavailableError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def search(self, query: str, limit: int) -> list[SearchResult]:

        try:
            response = await self.client.get(
                f"{self.base_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
                timeout=self.timeout,
            )
        except httpx.ConnectError as e:
            raise SearXNGUnavailableError(f"SearXNG is unavailable: {e}") from e
        except httpx.TimeoutException as e:
            raise SearXNGUnavailableError(f"SearXNG is not responding in time: {e}") from e

        if response.status_code == 503:
            raise SearXNGUnavailableError(f"SearXNG returned 503: {response.text}")

        if response.status_code >= 400:
            raise httpx.HTTPError(f"SearXNG error {response.status_code}: {response.text}")

        data = response.json()
        raw_results = data.get("results", [])

        return [
            SearchResult(
                url=item["url"],
                title=item.get("title", ""),
                snippet=item.get("content", ""),
                score=item.get("score"),
                source="searxng",
            )
            for item in raw_results[:limit]
            if item.get("url")
        ]