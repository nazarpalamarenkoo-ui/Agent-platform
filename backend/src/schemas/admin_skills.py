from datetime import datetime

from pydantic import BaseModel, Field


class AdminSkillListItem(BaseModel):
    id: int
    skill_name: str
    description: str
    archived_at: datetime | None = None
    updated_at: datetime
    model_config = {"from_attributes": True}


class AdminSkillRead(AdminSkillListItem):
    content: str
    owner_id: int | None = None


class ArchiveForViolation(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class AccessLogEntry(BaseModel):
    id: int
    admin_id: int | None
    skill_id: int | None
    action: str
    note: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class AdminToolItem(BaseModel):
    id: int
    tool_name: str
    description: str
    url_masked: str
    archived_at: datetime | None = None


class UserOverview(BaseModel):
    user_id: int
    private_skills: int
    private_tools: int
    bundles: int
    token_events: int
    tokens_used: int
    token_limit: int