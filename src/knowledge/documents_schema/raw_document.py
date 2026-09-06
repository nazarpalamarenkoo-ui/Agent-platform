from pydantic import BaseModel, Field
from datetime import datetime

class RawDocument(BaseModel):
    
    source: str
    content: bytes
    content_type: str
    content_hash: str = Field(min_length=64, max_length=64)
    fetched_at: datetime