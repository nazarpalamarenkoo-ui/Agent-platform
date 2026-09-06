from pydantic import BaseModel, Field

class KnowledgeChunk(BaseModel):
    document_id: int | None = None
    chunk_index: int
    text: str
    token_count: int
    metadata: dict = Field(default_factory=dict)