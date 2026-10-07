import hashlib
from src.knowledge.acquisition.dedup.url_normalizer import normalize_url, calculate_hash
from src.knowledge.documents_schema.discovery_model import DiscoveryResult
from src.repositories.discovered_document_repo import DiscoveredDocumentRepository


class Deduplicator:
    
    def __init__(self, discover_doc: DiscoveredDocumentRepository):
        
        self.discover_doc = discover_doc
        
    async def remove_duplicates(self, discover_docs: list[DiscoveryResult]) -> list[DiscoveryResult]:
        url_hashes = [calculate_hash(doc) for doc in discover_docs]

        existing_hashes = await self.discover_doc.get_existing_url_hashes(url_hashes)

        return [
            doc
            for doc, url_hash in zip(discover_docs, url_hashes)
            if url_hash not in existing_hashes
        ]