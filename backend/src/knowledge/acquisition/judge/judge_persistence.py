
from src.db.enums.discovery_type import DiscoveredDocumentDecision
from src.knowledge.acquisition.judge.models import DecidedSource, DocumentDecision
from src.repositories.discovered_document_repo import DiscoveredDocumentRepository
from src.schemas.discovered_document import DiscoveredDocumentCreate
from src.knowledge.acquisition.dedup.url_normalizer import normalize_url, calculate_hash_from_url

_DECISION_MAP = {
    DocumentDecision.ACCEPT: DiscoveredDocumentDecision.ACCEPT,
    DocumentDecision.REJECT: DiscoveredDocumentDecision.REJECT,
}

class JudgePersistence:
    
    def __init__(self, repo: DiscoveredDocumentRepository):
        
        self.repo = repo
        
    async def save(self, decided: list[DecidedSource]) -> None:
        filtered = [
            decided_source
            for decided_source in decided
            if decided_source.source.document_category != "judge_error"
        ]

        if not filtered:
            return None

        records = [
            DiscoveredDocumentCreate(
                url=item.source.url,
                url_hash=calculate_hash_from_url(item.source.url),
                decision=_DECISION_MAP[item.decision],
                trust_score=item.overall_score,
                educational_score=item.source.trust.educational,
                implementation_score=item.source.trust.implementation,
                authority_score=item.source.trust.authority,
                document_category=item.source.document_category,
                reason=item.source.reason,
            )
            for item in filtered
        ]

        await self.repo.save_all(records)