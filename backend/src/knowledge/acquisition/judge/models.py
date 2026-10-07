from enum import Enum

from pydantic import BaseModel, Field


class TrustBreakdown(BaseModel):
    educational: float = Field(ge=0.0, le=1.0)
    implementation: float = Field(ge=0.0, le=1.0)
    authority: float = Field(ge=0.0, le=1.0)


class JudgeItem(BaseModel):
    key: str
    trust: TrustBreakdown
    document_category: str
    reason: str


class JudgeResponse(BaseModel):
    results: list[JudgeItem]


class JudgeSource(BaseModel):
    key: str
    url: str
    title: str
    trust: TrustBreakdown
    document_category: str
    reason: str


class DocumentDecision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


class DecidedSource(BaseModel):
    source: JudgeSource
    decision: DocumentDecision
    overall_score: float