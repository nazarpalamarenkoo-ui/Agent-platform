import logging

from pydantic import ValidationError
from src.rag.retrieval.agentic.exceptions import LLMParseError
from src.rag.retrieval.agentic.llm_client import LLMClient
from src.rag.retrieval.agentic.models import SearchPlan
from src.rag.retrieval.agentic.prompts import PLANNER_SYSTEM, PLANNER_USER_TEMPLATE

logger = logging.getLogger(__name__)

class LLMPlanner:
    
    def __init__(self, llm_client: LLMClient):
        
        self.llm_client = llm_client
        
    async def create(self, query: str, knowledge_packs: list[str]) -> SearchPlan:
        packs_str = ", ".join(knowledge_packs)
        prompt = PLANNER_USER_TEMPLATE.format(
            query = query,
            knowledge_packs = packs_str
        )
        
        try:
            response = await self.llm_client.complete_json(prompt=prompt, system=PLANNER_SYSTEM)
            
            return SearchPlan(subqueries=response["subqueries"], reasoning=response.get("reasoning", ""))
            
        except (LLMParseError, ValidationError, KeyError) as e:
            logger.warning(f"LLMPlanner fallback: {e}")
            return SearchPlan(subqueries=[query])
        
        