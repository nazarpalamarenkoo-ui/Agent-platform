from pydantic import BaseModel, Field


class ConfigBundleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class BundleItems(BaseModel):
    skill_ids: list[int] = Field(default_factory=list)
    tool_ids: list[int] = Field(default_factory=list)
    knowledge_pack_ids: list[int] = Field(default_factory=list)


class EffectiveSkillRead(BaseModel):
    id: int
    name: str
    content_hash: str
    archived: bool
    model_config = {"from_attributes": True}


class EffectiveToolRead(BaseModel):
    id: int
    name: str
    url: str
    auth_type: str
    archived: bool
    model_config = {"from_attributes": True}


class EffectivePackRead(BaseModel):
    id: int
    slug: str
    version: int
    archived: bool
    model_config = {"from_attributes": True}


class EffectiveBundleRead(BaseModel):
    bundle_id: int
    agent_id: int
    agent_name: str
    skills: list[EffectiveSkillRead]
    tools: list[EffectiveToolRead]
    packs: list[EffectivePackRead]
    version_hash: str
    model_config = {"from_attributes": True}