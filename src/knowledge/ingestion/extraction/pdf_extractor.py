import fitz
from src.knowledge.documents_schema.text_span import TextSpan
from src.knowledge.ingestion.extraction.registry import ExtractorRegistry
from src.knowledge.ingestion.extraction.base_extractor import BaseExtractor, ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument

@ExtractorRegistry.register('application/pdf')
class PdfExtractor(BaseExtractor):
    
    def extract(self, document: RawDocument) -> ExtractedDocument:
        
        with fitz.open(stream=document.content, filetype = 'pdf') as pdf:
            
            spans = []
            text_parts = []
            cursor = 0
                     
            for page_num in range(pdf.page_count):
                
                page = pdf[page_num]
                page_text = page.get_text("text")
                
                start_char = cursor
                end_char = cursor + len(page_text)
                
                spans.append(TextSpan(
                    page = page_num,
                    section = None,
                    chapter = None,
                    heading = None,
                    start_char = start_char,
                    end_char = end_char
                ))
                
                text_parts.append(page_text)
                cursor = end_char + 2
                
            full_text = "\n\n".join(text_parts)
            
        return ExtractedDocument(
            text=full_text,
            metadata={
                "page_count": pdf.page_count,
                "source": document.source,
            },
            spans = spans
        )    
            