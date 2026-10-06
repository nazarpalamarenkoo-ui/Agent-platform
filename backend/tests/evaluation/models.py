from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class RetrievalExample(BaseModel):
    id: str
    query: str
    knowledge_packs: list[str]
    relevant_chunk_ids: list[str]


class RetrievalPrediction(BaseModel):
    retrieved_chunk_ids: list[str]


class ModeResult(BaseModel):
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float


class AgenticModeResult(ModeResult):
    avg_iterations: float
    degraded_to_hybrid_pct: float
    avg_coverage: float
    avg_confidence: float


class PerQueryResult(BaseModel):
    id: str
    query: str
    relevant_count: int
    hybrid_recall_at_10: float | None = None
    hybrid_mrr: float | None = None
    hybrid_ndcg_at_10: float | None = None
    agentic_recall_at_10: float | None = None
    agentic_mrr: float | None = None
    agentic_ndcg_at_10: float | None = None
    agentic_iterations: int | None = None
    agentic_degraded: bool | None = None


class DeltaResult(BaseModel):
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float


class BenchmarkMeta(BaseModel):
    timestamp: str
    mode: Literal["hybrid", "agentic", "both"]
    dataset_size: int
    config: dict


class BenchmarkResult(BaseModel):
    meta: BenchmarkMeta
    hybrid: ModeResult | None = None
    agentic: AgenticModeResult | None = None
    delta: DeltaResult | None = None
    per_query: list[PerQueryResult] = []