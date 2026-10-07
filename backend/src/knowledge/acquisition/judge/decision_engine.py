import math

from src.knowledge.acquisition.judge.models import DecidedSource, JudgeSource, TrustBreakdown, DocumentDecision

class DecisionEngine:
    
    def __init__(
        self, 
        educational_weight: float = 0.45, 
        implementation_weight: float = 0.35, 
        authority_weight: float = 0.20, 
        acceptance_threshold: float = 0.65
    ):
        
        self.educational_weight = educational_weight
        self.implementation_weight = implementation_weight
        self.authority_weight = authority_weight
        self.acceptance_threshold = acceptance_threshold
        
        if not math.isclose(self.educational_weight + self.implementation_weight + self.authority_weight, 1.0):
            raise ValueError('sum must be 1.0')
        
        if not 0.0 <= acceptance_threshold <= 1.0:
            raise ValueError("acceptance_threshold must be between 0.0 and 1.0")
        
    def _calculate_overall(self, trust: TrustBreakdown) -> float:
        
        overall = round(
            trust.educational * self.educational_weight +
            trust.implementation * self.implementation_weight +
            trust.authority * self.authority_weight,
            3
        )
        
        return overall
        
    def decide(self, source: JudgeSource) -> DecidedSource:
        
        if source.document_category == 'judge_error':
            return DecidedSource(source = source, decision=DocumentDecision.REJECT, overall_score=0.0)
        
        score = self._calculate_overall(source.trust)
        
        decision = (
            DocumentDecision.ACCEPT
            if score >= self.acceptance_threshold
            else DocumentDecision.REJECT
        )

        return DecidedSource(
            source=source,
            decision=decision,
            overall_score=score,
        )
        
    def decide_many(self, sources: list[JudgeSource]) -> list[DecidedSource]:
        
        return [self.decide(source) for source in sources]