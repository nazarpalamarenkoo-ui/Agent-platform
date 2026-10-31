from pydantic import BaseModel

from src.db.enums.tool_auth_type import ToolAuthType

class ToolCreate(BaseModel):
    tool_name: str
    description: str
    url: str
    auth_type: ToolAuthType = ToolAuthType.NONE
    auth_description: str | None = None
    domain_ids: list[int] = []

class ToolRead(BaseModel):
    id: int
    tool_name: str
    description: str
    url: str
    auth_type: ToolAuthType
    auth_description: str | None = None
    tool_selected_freq: int
    model_config = {"from_attributes": True}