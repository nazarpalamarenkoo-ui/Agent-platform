from pydantic import BaseModel

class DomainCreate(BaseModel):
    slug: str
    name: str
    description: str
    parent_domain_id: int | None = None

class DomainRead(BaseModel):
    id: int
    slug: str
    name: str
    description: str
    parent_domain_id: int | None = None
    children: list["DomainRead"] = []
    model_config = {"from_attributes": True}

DomainRead.model_rebuild()