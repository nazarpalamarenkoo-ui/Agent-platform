import trafilatura
from src.knowledge.documents_schema.text_span import TextSpan
from src.knowledge.ingestion.extraction.registry import ExtractorRegistry
from src.knowledge.ingestion.extraction.base_extractor import BaseExtractor, ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument


@ExtractorRegistry.register('text/html')
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
        spans = []
        
        spans.append(TextSpan(page=None, section=None, chapter = None, heading=None, start_char=0, end_char=len(text)))
        
        return ExtractedDocument(text=text, metadata={"source": document.source}, spans = spans)