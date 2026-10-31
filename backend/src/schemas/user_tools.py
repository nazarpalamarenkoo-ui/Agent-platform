from datetime import datetime

from pydantic import BaseModel, Field

from src.db.enums.tool_auth_type import ToolAuthType


class MyToolCreate(BaseModel):
    tool_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    auth_type: ToolAuthType = ToolAuthType.NONE
    auth_description: str | None = Field(default=None, max_length=255)
    domain_ids: list[int] = Field(default_factory=list)


class MyToolUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    auth_type: ToolAuthType | None = None
    auth_description: str | None = Field(default=None, max_length=255)


class MyToolRead(BaseModel):
    id: int
    tool_name: str
    description: str
    url: str
    auth_type: ToolAuthType
    auth_description: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class MyToolResponse(BaseModel):
    tool: MyToolRead
    warnings: list[str] = Field(default_factory=list)