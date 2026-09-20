import httpx
import hashlib
import mimetypes
from datetime import datetime, timezone

from src.knowledge.documents_schema.raw_document import RawDocument 

class FetcherUnavailableError(Exception):
    pass

class Fetcher:
    
    def __init__(self, client: httpx.AsyncClient, timeout: float = 10.0):
        self.client = client
        self.timeout = timeout
        
    async def fetch(self, url: str) -> RawDocument:

        try:
            response = await self.client.get(url, timeout=self.timeout)
            
        except httpx.ConnectError as e:
            raise FetcherUnavailableError(f"Fetcher is unavailable: {e}") from e
        except httpx.TimeoutException as e:
            raise FetcherUnavailableError(f"Fetcher is not responding in time: {e}") from e
    
        if response.status_code == 503:
            raise FetcherUnavailableError(f"Fetcher returned 503: {response.text}")
        if response.status_code >= 400:
            raise httpx.HTTPError(f"Fetcher error {response.status_code}: {response.text}")
        
        content_type = response.headers.get("content-type", "").split(";")[0].strip()

        if not content_type or content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(url)
            content_type = guessed or "text/html"
        
        return RawDocument(
            source=url,
            content=response.content,
            content_type=content_type,
            content_hash=hashlib.sha256(response.content).hexdigest(),
            fetched_at=datetime.now(timezone.utc)
        )
        