import tiktoken
from src.knowledge.documents_schema.embeddend_chunk import KnowledgeChunk
from src.knowledge.documents_schema.text_span import TextSpan
from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument

class Chuncking:
    
    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.encoder = tiktoken.get_encoding('cl100k_base')
    
    def _find_span(self, char_pos: int, spans: list[TextSpan]) -> TextSpan | None:
    
        for span in spans:
            if span.start_char <= char_pos < span.end_char:
                return span
        
        return None
    
    def chunk(self, extracted: ExtractedDocument) -> list[KnowledgeChunk]:
        
        token_ids = self.encoder.encode(extracted.text)
        
        chunks = []
        step = self.chunk_size - self.overlap
        
        for i, start in enumerate(range(0, len(token_ids), step)):
            end = start + self.chunk_size
            chunk_tokens = token_ids[start:end]
            
            if len(chunk_tokens) == 0:
                break
            
            text = self.encoder.decode(chunk_tokens)
            
            char_pos = len(self.encoder.decode(token_ids[:start]))
            
            span = self._find_span(char_pos, extracted.spans)
            
            chunks.append(KnowledgeChunk(
                document_id=None,
                chunk_index=i,
                text=text,
                token_count=len(chunk_tokens),
                metadata={
                    "source": extracted.metadata.get("source"),
                    "page": span.page if span else None,
                    "section": span.section if span else None,
                    "chapter": span.chapter if span else None,
                    "heading": span.heading if span else None,
                }
            ))
        
        return chunks
        
       