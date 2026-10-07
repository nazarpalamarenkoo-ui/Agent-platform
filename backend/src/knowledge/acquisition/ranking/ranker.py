import re
from typing import Optional

from src.knowledge.documents_schema.discovery_model import DiscoveryResult
DOMAIN_SCORES = {
    'arxiv.org': 0.35,
    'acm.org': 0.35,
    'ieee.org': 0.35,
    'microsoft.com': 0.30,
    'google.com': 0.30,
    'github.com': 0.25,
    'medium.com': 0.05,
    'dou.ua': 0.03
}
FORMAT_SCORES = {
    'application/pdf': 0.40,
    'text/html': 0.35,
    'text/plain': 0.25
}

class Ranker:
    
    def __init__(
        self,
        domain_scores: Optional[dict[str, float]] = None,
        format_scores: Optional[dict[str, float]] = None,
        top_n: int = 15,
        default_domain_score: float = 0.1,
        default_format_score: float = 0.1,
    ):
        self.domain_scores = domain_scores if domain_scores is not None else DOMAIN_SCORES
        self.format_scores = format_scores if format_scores is not None else FORMAT_SCORES
        self.top_n = top_n
        self.default_domain_score = default_domain_score
        self.default_format_score = default_format_score
        
    def _domain_score(self, result: DiscoveryResult) -> float:
        return self.domain_scores.get(result.domain, self.default_domain_score)

    def _format_score(self, result: DiscoveryResult) -> float:
        return self.format_scores.get(result.mime_type, self.default_format_score)
    
    def _tokenize(self, query: str) -> set[str]:
        return set(re.findall(r"\w+", query.lower()))
    
    def _title_similarity(self, query: str, result: DiscoveryResult) -> float:
        
        query_token = self._tokenize(query)
        title_token = self._tokenize(result.title)
        
        if not query_token:
            return 0.0
        
        overlap = query_token & title_token
        return len(overlap) / len(query_token)
    
    def _keyword_overlap(self, query: str, result: DiscoveryResult) -> float:
        
        query_token = self._tokenize(query)
        snippet_token = self._tokenize(result.snippet)
        
        if not query_token:
            return 0.0
                
        overlap = query_token & snippet_token
        return len(overlap) / len(query_token)
    
    def _calculate_score(self, query: str, result: DiscoveryResult) -> float:
        
        domain_score = self._domain_score(result)
        format_score = self._format_score(result)
        title_similar = self._title_similarity(query, result)
        keyword_over = self._keyword_overlap(query, result)
        
        rank_score = domain_score + format_score + title_similar + keyword_over
        
        return rank_score
    
    def rank(self, query: str, results: list[DiscoveryResult]) -> list[DiscoveryResult]:
        
        if not query:
            return []
        
        results = sorted(
            results,
            key=lambda result: self._calculate_score(query, result),
            reverse=True,
        )[:self.top_n]
        
        
        return results