from pydantic import BaseModel, Field

class CustomAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=255)
    skill_ids: list[int] = Field(default_factory=list)
    tool_ids: list[int] = Field(default_factory=list)
    knowledge_pack_ids: list[int] = Field(default_factory=list)


class _Ref(BaseModel):
    id: int
    model_config = {"from_attributes": True}


class CustomAgentRead(BaseModel):
    id: int
    name: str
    description: str
    agent_id: int
    skills: list[_Ref]
    tools: list[_Ref]
    knowledge_packs: list[_Ref]
    model_config = {"from_attributes": True}
    
class AgentCreate(BaseModel):
    
    name: str
    description: str
    skill_ids: list[int]
    tool_ids: list[int]
    
class SkillRead(BaseModel):
    
    id: int
    skill_name: str
    description: str
    model_config = {"from_attributes": True}
    
class ToolRead(BaseModel):
    
    id: int
    tool_name: str
    description: str
    model_config = {"from_attributes": True}
    
class AgentRead(BaseModel):
    
    id: int
    agent_name: str
    description: str
    skills: list[SkillRead]
    tools: list[ToolRead]
    model_config = {"from_attributes": True}
    