from src.knowledge.ingestion.extraction.registry import ExtractorRegistry
from src.knowledge.ingestion.extraction.base_extractor import BaseExtractor, ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument

@ExtractorRegistry.register('text/plain')
class TextExtractor(BaseExtractor):
    
    def extract(self, document: RawDocument) -> ExtractedDocument:
        
        text = document.content.decode("utf-8")
        
        return ExtractedDocument(
            text=text,
            metadata={
                "source": document.source,
            }
        )