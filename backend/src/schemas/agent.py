from pydantic import BaseModel

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
    