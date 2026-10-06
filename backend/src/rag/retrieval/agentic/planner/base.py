from typing import Protocol

from src.rag.retrieval.agentic.models import SearchPlan

class BasePlanner(Protocol):
    
    async def create(self, query: str, knowledge_packs: list[str]) -> SearchPlan:
        pass