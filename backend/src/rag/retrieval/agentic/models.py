from pydantic import BaseModel, Field, model_validator


class SearchPlan(BaseModel):
    subqueries: list[str] = Field(description="List of subqueries, maximum of 5")
    reasoning: str = Field(default="")

    @model_validator(mode="after")
    def limit_subqueries(self) -> "SearchPlan":
        self.subqueries = self.subqueries[:5]
        return self


class RetrievalEvidence(BaseModel):
    query: str = Field(description="The subquery that produced this result")
    chunk_id: str
    score: float = Field(
        description="Ranking score. For a single search hit this is the raw "
        "reranker score; after the orchestrator merges results it is the "
        "fused (weighted RRF) score, so sorting by it gives the final order."
    )
    raw_score: float | None = Field(
        default=None,
        description="Best raw reranker score this chunk got in any single "
        "search. Set by the orchestrator when it fuses results.",
    )
    text: str
    metadata: dict = Field(default_factory=dict)


class RetrievalEvaluation(BaseModel):
    sufficient: bool = Field(
        description="Is there enough context to answer the question?"
    )
    coverage: float = Field(
        ge=0.0, le=1.0,
        description="Percentage of subqueries that returned results"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Average score of the results found"
    )
    redundancy: float = Field(
        ge=0.0, le=1.0,
        description="Percentage of duplicates among the results"
    )
    missing_topics: list[str] = Field(
        default_factory=list,
        description="Topics that were not found (from LLMEvaluator)"
    )
    retry_queries: list[str] = Field(
        default_factory=list,
        description="Subqueries for a repeat search"
    )


class IterationRecord(BaseModel):
    iteration: int
    subqueries: list[str] = Field(
        description="Subqueries actually searched on this iteration "
        "(already-searched queries are skipped)"
    )
    new_evidence_count: int = Field(
        description="Raw hits returned by the searches of this iteration "
        "(includes chunks already seen before)"
    )
    total_evidence_count: int = Field(
        description="Cumulative raw hits when evaluation ran"
    )
    new_unique_count: int = Field(
        default=0,
        description="Chunks this iteration added that had not been seen before"
    )
    total_unique_count: int = Field(
        default=0,
        description="Unique chunks accumulated when evaluation ran"
    )
    evaluation: RetrievalEvaluation


class AgenticContext(BaseModel):
    original_query: str
    plan: SearchPlan
    evidence: list[RetrievalEvidence] = Field(
        default_factory=list,
        description="FINAL result: unique chunks, ranked best-first by "
        "weighted RRF over all searches. Use this for context building "
        "and metrics."
    )
    raw_evidence: list[RetrievalEvidence] = Field(
        default_factory=list,
        description="Every hit of every search, in search order, with "
        "duplicates. For debugging only."
    )
    evaluation: RetrievalEvaluation | None = None
    iteration: int = Field(default=1)
    iterations: list[IterationRecord] = Field(
        default_factory=list,
        description="Full history of the agentic loop, one record per "
        "completed iteration. Empty when the run degraded to hybrid "
        "fallback (no evaluation ever ran)."
    )


def to_evidence(query: str, result) -> RetrievalEvidence:
    return RetrievalEvidence(
        query=query,
        chunk_id=str(result.id),
        score=float(result.score),
        text=result.payload.get("text", ""),
        metadata=result.payload,
    )