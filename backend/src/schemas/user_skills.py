from datetime import datetime

from pydantic import BaseModel, Field

from src.db.enums.skill_visibility import SkillVisibility


class MySkillCreate(BaseModel):
    skill_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=50_000)
    domain_ids: list[int] = Field(default_factory=list)


class MySkillImport(BaseModel):
    markdown: str = Field(min_length=1, max_length=60_000)
    skill_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    domain_ids: list[int] = Field(default_factory=list)


class MySkillUpdate(BaseModel):
    skill_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=50_000)


class MySkillSummary(BaseModel):
    id: int
    skill_name: str
    description: str
    content_hash: str
    visibility: SkillVisibility
    archived_at: datetime | None
    model_config = {"from_attributes": True}


class MySkillRead(MySkillSummary):
    content: str
    created_at: datetime
    updated_at: datetime