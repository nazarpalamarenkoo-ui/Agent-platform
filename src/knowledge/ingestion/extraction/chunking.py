import tiktoken
from src.knowledge.documents_schema.embeddend_chunk import KnowledgeChunk
from src.knowledge.ingestion.extraction.base_extractor import ExtractedDocument

class Chuncking:
    
    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.encoder = tiktoken.get_encoding('cl100k_base')
    
    def _get_page(self, extracted: ExtractedDocument, token_start: int, token_ids: list) -> int | None:
        
        pages = extracted.metadata.get('pages')
        
        if not pages:
            return None
        
        char_pos = len(self.encoder.decode(token_ids[:token_start]))
        current_pos = 0
        
        for page in pages:
            current_pos += len(page['text'])
            if char_pos <= current_pos:
                return page['page']
        
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
            
            chunks.append(KnowledgeChunk(
                document_id=None,
                chunk_index=i,
                text=text,
                token_count=len(chunk_tokens),
                metadata={
                    "source": extracted.metadata.get("source"),
                    "page": self._get_page(extracted, start, token_ids),
                }
            ))
        
        return chunks
        
       