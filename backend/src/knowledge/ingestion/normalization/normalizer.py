import re
import unicodedata
from collections import Counter
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk

class Normalizer:
    
    def __init__(self, min_lenght: int = 50, boilerplate_threshold: float = 0.7):
        
        self.min_lenght = min_lenght
        self.boilerplate_threshold = boilerplate_threshold
        
    def find_boilerplate(self, chunks: list[KnowledgeChunk]) -> set[str]:
        
        line_counts = Counter()
        
        for chunk in chunks:
            lines = set(chunk.text.splitlines())
            line_counts.update(lines)
            
        threshold = len(chunks) * self.boilerplate_threshold
        return {line for line, count in line_counts.items() if count >= threshold and line.strip()}
        
    def _remove_boilerplate(self, text: str, boilerplate: set[str]) -> str:
        
        lines = text.splitlines()
        
        cleaned = [line for line in lines if line.strip() not in boilerplate]
        
        return "\n".join(cleaned)
    
    def normalize(self, chunks: list[KnowledgeChunk], boilerplate: set[str] | None = None) -> list[KnowledgeChunk]:
        
        if boilerplate is None:
            boilerplate = self.find_boilerplate(chunks)
        
        result = []
        
        for chunk in chunks:
            text = chunk.text
            text = unicodedata.normalize('NFKC', text)
            text = re.sub(r'\s+', ' ', text).strip()
            text = self._remove_boilerplate(text, boilerplate)
            
            if len(text) < self.min_lenght:
                continue
            
            result.append(chunk.model_copy(update = {'text': text}))
            
        return result