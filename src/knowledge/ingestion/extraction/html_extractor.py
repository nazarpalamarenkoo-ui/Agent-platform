import trafilatura
from src.knowledge.ingestion.extraction.base_extractor import BaseExtractor, ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument



class HTMLExtractor(BaseExtractor):
    def extract(self, document: RawDocument) -> ExtractedDocument:
        text = trafilatura.extract(
            document.content,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if not text:
            text = ""
        return ExtractedDocument(text=text, metadata={"source": document.source})