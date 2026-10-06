from src.rag.retrieval.agentic.models import SearchPlan
from yake import KeywordExtractor

class HeuristicPlanner:
    
    def __init__(self, top_n: int = 5, language: str = "en", n: int = 3, max_len: int = 300):
        self.top_n = top_n
        self.language = language
        self.n = n
        self.max_len = max_len
        
    async def create(self, query: str, knowledge_packs: list[str]) -> SearchPlan:
        
        if not query:
            return SearchPlan(subqueries = [])
        
        extractor = KeywordExtractor(lan = self.language, n = self.n, top = self.top_n)
        
        results = extractor.extract_keywords(query)
        
        keywords = [
            word[0] for word in results
            if 2 < len(word[0]) < self.max_len
        ]
        
        sub_queries = [query]
        
        for kw in keywords[:3]:
            if kw.lower() != query.lower() and kw not in sub_queries:
                sub_queries.append(kw)
                
        return SearchPlan(subqueries=sub_queries[:4])
        
        