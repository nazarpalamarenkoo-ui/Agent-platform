from pydantic import BaseModel

class TextSpan(BaseModel):
    page: int | None
    section: str | None
    chapter: str | None
    heading: str | None
    start_char: int
    end_char: int