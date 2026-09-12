# config_bundle.py
from pydantic import BaseModel
from src.schemas.agent import SkillRead, ToolRead
from src.schemas.knowledge_pack import KnowledgePackRead

class ConfigBundleCreate(BaseModel):
    agent_id: int
    name: str
    description: str
    skill_ids: list[int]
    tool_ids: list[int]
    knowledge_pack_ids: list[int] = []

class ConfigBundleFromAgent(BaseModel):
    agent_id: int
    name: str
    description: str

class ConfigBundleRead(BaseModel):
    id: int
    user_id: int
    agent_id: int
    name: str
    description: str
    skills: list[SkillRead]
    tools: list[ToolRead]
    knowledge_packs: list[KnowledgePackRead]
    model_config = {"from_attributes": True}