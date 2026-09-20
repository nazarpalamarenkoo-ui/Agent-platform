from pydantic import BaseModel
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType

class IngestFileRequest(BaseModel):
    source: str
    document_type: DocumentType
    knowledge_type: KnowledgeType
    knowledge_pack_id: int

class IngestWebRequest(BaseModel):
    query: str
    limit: int = 5
    document_type: DocumentType
    knowledge_type: KnowledgeType
    knowledge_pack_id: int
    
class SearchRequest(BaseModel):
    query: str
    limit: int = 20
    top_n: int = 5
    k: int = 60
    config_bundle_id: int
    
class SearchResultResponse(BaseModel):
    id: str
    score: float
    payload: dict