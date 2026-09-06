import hashlib
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk


class Validator:
    
    def __init__(self, min_lenght: int = 50) -> None:
        
        self.min_lenght = min_lenght
        self._seen_hashes: set[str] = set()
        
    def validate(self, chunk: KnowledgeChunk) -> bool:
        
        if len(chunk.text) < self.min_lenght:
            return False
        
        chunk_hash = hashlib.md5(chunk.text.encode()).hexdigest()
    
        if chunk_hash in self._seen_hashes:
            return False
        
        self._seen_hashes.add(chunk_hash)
        return True
    
    def reset(self) -> None:
        self._seen_hashes.clear()