from pydantic import BaseModel, Field

from src.db.enums.tool_auth_type import ToolAuthType


class SkillUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=50_000)


class ToolUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=2048)
    auth_type: ToolAuthType | None = None
    auth_description: str | None = Field(default=None, max_length=255)


class AgentUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    skill_ids: list[int] | None = None
    tool_ids: list[int] | None = None