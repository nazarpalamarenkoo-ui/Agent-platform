from pydantic import BaseModel, Field
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk

class EmbeddedChunk(BaseModel):
    chunk: KnowledgeChunk

    dense_vector: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]