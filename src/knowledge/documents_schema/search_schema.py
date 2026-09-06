from pydantic import BaseModel, Field

class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str
    score: float | None = None
    source: str | None = None
    engines: list[str] = Field(default_factory=list)