from src.rag.embeddings.bge_m3 import Embedding, EmbeddingResult

class QueryEncoder:
    
    def __init__(self, embedding: Embedding):
        
        self.embedding = embedding
        
    def encode(self, query: str)  -> EmbeddingResult:
        
        embedding_result = self.embedding.embed([query])[0]
        
        return embedding_result