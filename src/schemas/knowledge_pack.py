from pydantic import BaseModel

class KnowledgePackCreate(BaseModel):
    name: str
    domain_id: int
    description: str
    slug: str

class KnowledgePackRead(BaseModel):
    id: int
    name: str
    slug: str
    domain_id: int
    description: str
    version: int
    model_config = {"from_attributes": True}