from pydantic import BaseModel


class DocumentCandidate(BaseModel):
    key: str

    query: str

    title: str
    url: str
    domain: str
    snippet: str

    headings: list[str]
    first_page: str