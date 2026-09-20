import os
import hashlib
from datetime import datetime, timezone

from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.ingestion.loaders.base_loader import BaseLoader
from src.knowledge.ingestion.loaders.registry import LoaderRegistry


@LoaderRegistry.register('application/pdf')
class PDFLoader(BaseLoader):
    
    def load_document(self, source: str) -> RawDocument:
        
        if not os.path.isfile(source):
            raise FileNotFoundError(f"Error: File '{source}' does not exist.")
        
        if not source.lower().endswith(".pdf"):
            raise ValueError("Error: The file is not a PDF.")
        
        with open(source, 'rb') as f:
            content = f.read()

        return RawDocument(
            source = source,
            content = content,
            content_type="application/pdf",
            content_hash=hashlib.sha256(content).hexdigest(),
            fetched_at=datetime.now(timezone.utc),
        )