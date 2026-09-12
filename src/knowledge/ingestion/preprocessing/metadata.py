from yake import KeywordExtractor
class TagExtractor:
    
    def __init__(self, top_n: int = 5):
        self.top_n = top_n

    
    def extract_tags(self, text: str, language: str = "en", top_n: int | None = None) -> list[str]:
        if not text or not text.strip():
            return []
        
        n = top_n or self.top_n
        
        lan = language if language != "unknown" else "en"
        
        extractor = KeywordExtractor(lan=lan, top=n)
        results = extractor.extract_keywords(text)
    
        return [keyword for keyword, score in results]