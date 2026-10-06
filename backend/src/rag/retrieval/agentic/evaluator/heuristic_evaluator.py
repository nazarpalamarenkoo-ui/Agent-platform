from typing import List, Dict
from src.rag.retrieval.agentic.models import RetrievalEvaluation, RetrievalEvidence

class HeuristicEvaluator:
    
    def __init__(self, coverage_threshold: float = 0.5, confidence_threshold: float = 0.5, success_threshold: float = 0.6):
        self.coverage_threshold = coverage_threshold
        self.confidence_threshold = confidence_threshold
        self.success_threshold = success_threshold

    async def evaluate(self, query: str, evidences: List[RetrievalEvidence]) -> RetrievalEvaluation:
        
        if not evidences:
            
            return RetrievalEvaluation(
                coverage=0.0,
                confidence=0.0,
                redundancy=0.0,
                sufficient=False,
                missing_topics=[],
                retry_queries=[]
            )

        grouped_by_query = {}
        for ev in evidences:
            if ev.query not in grouped_by_query:
                grouped_by_query[ev.query] = []
            grouped_by_query[ev.query].append(ev.score)
        
        unique_queries = len(grouped_by_query)
        successful_queries = 0
        for q, scores in grouped_by_query.items():
            if any(s > self.coverage_threshold for s in scores):
                successful_queries += 1
        coverage = successful_queries / unique_queries

        all_scores = [ev.score for ev in evidences]
        confidence = sum(all_scores) / len(all_scores)

        chunk_ids = [ev.chunk_id for ev in evidences]
        unique_chunk_ids = set(chunk_ids)
        redundancy = (len(chunk_ids) - len(unique_chunk_ids)) / len(chunk_ids)

        is_sufficient = (coverage > self.success_threshold) and (confidence > self.confidence_threshold)

        return RetrievalEvaluation(
            coverage=coverage,
            confidence=confidence,
            redundancy=redundancy,
            sufficient=is_sufficient,
            missing_topics=[], 
            retry_queries=[]
        )