from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.knowledge.documents_schema.corpus_build_result import CorpusBuilderResult


class IngestFileRequest(BaseModel):
    source: str
    document_type: DocumentType
    knowledge_type: KnowledgeType
    knowledge_pack_id: int


class IngestWebRequest(BaseModel):
    query: str
    document_type: DocumentType
    knowledge_type: KnowledgeType
    knowledge_pack_id: int


class JobCreatedResponse(BaseModel):
    job_id: int
    status: str


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    status: str
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


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


class SearchAgenticRequest(BaseModel):
    query: str
    config_bundle_id: int


class AgenticEvidenceResponse(BaseModel):
    query: str
    chunk_id: str
    score: float
    text: str
    metadata: dict


class EvaluationResponse(BaseModel):
    sufficient: bool
    coverage: float
    confidence: float
    redundancy: float
    missing_topics: list[str]
    retry_queries: list[str]


class IterationResponse(BaseModel):
    iteration: int
    subqueries: list[str]
    new_evidence_count: int
    total_evidence_count: int
    evaluation: EvaluationResponse


class SearchAgenticResponse(BaseModel):
    initial_subqueries: list[str]
    reasoning: str
    evidence: list[AgenticEvidenceResponse]
    iterations: list[IterationResponse]
    degraded_to_hybrid: bool