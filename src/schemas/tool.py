from pydantic import BaseModel

class ToolCreate(BaseModel):
    tool_name: str
    description: str
    domain_ids: list[int] = []

class ToolRead(BaseModel):
    id: int
    tool_name: str
    description: str
    tool_selected_freq: int
    model_config = {"from_attributes": True}