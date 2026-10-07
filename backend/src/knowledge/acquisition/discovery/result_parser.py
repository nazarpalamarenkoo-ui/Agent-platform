from urllib.parse import urlparse
import mimetypes

from src.knowledge.documents_schema.discovery_model import DiscoveryResult
from src.knowledge.documents_schema.search_schema import SearchResult

class ResultParser:
    
    def _extract_domain(self, url: str) -> str:
        if not url:
            return 'unknown'
        else:
            domain = urlparse(url).netloc.removeprefix('www.').lower()
        return domain
    
    def _guess_mime_type(self, url: str) -> str:
        
        mimetype, _ = mimetypes.guess_type(url)
        content_type = mimetype or "text/html"
        
        return content_type
    
    def _parse_one(self, result: SearchResult) -> DiscoveryResult | None:
        
        if not result.url:
            return None
        
        discovery = DiscoveryResult(
            title = result.title,
            url = result.url,
            domain = self._extract_domain(result.url),
            snippet=result.snippet,
            mime_type=self._guess_mime_type(result.url)
        )
        
        return discovery
    
    def parse_many(self, results: list[SearchResult]) -> list[DiscoveryResult]:
        
        return [parsed for r in results if (parsed := self._parse_one(r)) is not None]