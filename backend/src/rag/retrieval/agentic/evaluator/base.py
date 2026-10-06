from typing import Protocol, List

from src.rag.retrieval.agentic.models import RetrievalEvaluation, RetrievalEvidence

class BaseEvaluator(Protocol):
    
    async def evaluate(self, query: str, evidences: List[RetrievalEvidence]) -> RetrievalEvaluation:
        pass