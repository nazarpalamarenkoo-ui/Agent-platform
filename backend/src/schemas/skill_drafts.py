from pydantic import BaseModel, Field


class SkillDraftRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=2000)
    skill_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    source_text: str | None = Field(default=None, max_length=20_000)
    config_bundle_id: int | None = None
    knowledge_pack_ids: list[int] = Field(default_factory=list, max_length=10)
    search_queries: list[str] = Field(default_factory=list, max_length=3)
    auto_packs: bool = False


class PackRef(BaseModel):
    id: int
    slug: str
    name: str
    description: str


class PackSuggestion(BaseModel):
    packs: list[PackRef] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)


class SuggestPacksRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=2000)


class SkillDraftJobResponse(BaseModel):
    job_id: int
    status: str


class UsedPack(BaseModel):
    id: int | None = None
    slug: str
    name: str
    domain_id: int | None = None
    chunks: int = 0


class SkillDraftResult(BaseModel):
    skill_name: str
    description: str
    content: str
    grounded: bool
    sources: list[str] = Field(default_factory=list)
    used_packs: list[UsedPack] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SkillDraftStatus(BaseModel):
    job_id: int
    status: str
    error: str | None = None
    draft: SkillDraftResult | None = None


class SkillDraftConfirm(BaseModel):
    skill_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=50_000)
    domain_ids: list[int] = Field(default_factory=list)


class AttachPacksRequest(BaseModel):
    config_bundle_id: int


class AttachPacksResponse(BaseModel):
    bundle_id: int
    knowledge_pack_ids: list[int]