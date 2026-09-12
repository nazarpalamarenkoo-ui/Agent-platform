from pydantic import BaseModel

class CorpusBuilderResult(BaseModel):
    
    succeeded: list[int]
    skipped_duplicates: list[str]
    failed: list[dict]