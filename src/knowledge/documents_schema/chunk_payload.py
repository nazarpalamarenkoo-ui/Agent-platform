from pydantic import BaseModel

class ChunkPayload(BaseModel):
    
    document_id: int
    chunk_index: int
    text: str
    knowledge_pack: str
    domain: str
    language: str
    framework: str
    version: str
    source_type: str
    tags: list[str]
    quality_score: float
    title: str