import fitz

from src.knowledge.ingestion.extraction.base_extractor import BaseExtractor, ExtractedDocument
from src.knowledge.documents_schema.raw_document import RawDocument

class PdfExtractor(BaseExtractor):
    
    def extract(self, document: RawDocument) -> ExtractedDocument:
        
        with fitz.open(stream=document.content, filetype = 'pdf') as pdf:
            
            pages = []
            
            for page_num in range(pdf.page_count):
                
                page = pdf[page_num]
                text = page.get_text("text")
                pages.append({"page": page_num, "text": text})
            
            full_text = "\n\n".join(p["text"] for p in pages)
            
        return ExtractedDocument(
            text=full_text,
            metadata={
                "page_count": pdf.page_count,
                "pages": pages,
                "source": document.source,
            }
        )    
            