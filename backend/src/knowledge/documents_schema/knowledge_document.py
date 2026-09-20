from pydantic import BaseModel, Field
from datetime import datetime

class KnowledgeDocument(BaseModel):
    document_id: int | None = None

    title: str
    source: str
    source_type: str           

    topic: str
    summary: str

    text: str                 

    concepts: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    page: int | None = None
    section: str | None = None

    content_hash: str
    created_at: datetime