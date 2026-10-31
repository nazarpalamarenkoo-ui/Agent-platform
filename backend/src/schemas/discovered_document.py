from pydantic import BaseModel

from src.db.models.discovered_document import DiscoveredDocumentDecision


class DiscoveredDocumentCreate(BaseModel):
    url: str
    url_hash: str
    decision: DiscoveredDocumentDecision

    trust_score: float | None = None
    educational_score: float | None = None
    implementation_score: float | None = None
    authority_score: float | None = None

    document_category: str | None = None
    reason: str | None = None