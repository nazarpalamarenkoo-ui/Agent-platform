from pydantic import BaseModel, Field

class SearchFilter(BaseModel):
    knowledge_packs: list[str] | None = None
    domains: list[str] | None = None
    tags: list[str] | None = None
    language: str | None = None
    framework: str | None = None
    source_type: str | None = None