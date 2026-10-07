from pydantic import BaseModel

class DiscoveryResult(BaseModel):
    
    title: str
    url: str
    domain: str
    snippet: str
    mime_type: str