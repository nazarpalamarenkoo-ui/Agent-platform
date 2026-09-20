from datetime import datetime
from pydantic import BaseModel, Field
from src.db.enums.document_status import DocumentStatus
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType


class DocumentCreate(BaseModel):
    source: str
    document_type: DocumentType
    knowledge_type: KnowledgeType
    size: int
    content_hash: str = Field(min_length=64, max_length=64)
    scraped_at: datetime
    embedding_model: str
    embedding_version: str | None = None
    knowledge_pack_id: int | None = None


class DocumentRead(BaseModel):
    id: int
    source: str
    document_type: DocumentType
    knowledge_type: KnowledgeType
    size: int
    content_hash: str
    version: int
    scraped_at: datetime
    created_at: datetime
    status: DocumentStatus
    embedding_model: str
    embedding_version: str | None = None
    knowledge_pack_id: int | None = None

    model_config = {"from_attributes": True}