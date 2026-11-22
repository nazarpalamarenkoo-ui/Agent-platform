from pydantic import BaseModel, Field, field_validator

from src.catalog.hint.models import GapKind
from src.schemas.skill_drafts import SkillDraftResult


class HintRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=1000)

    @field_validator("intent")
    @classmethod
    def _strip_and_require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("intent cannot be blank")
        return value


class HintRef(BaseModel):
    id: int
    name: str


class HintItem(HintRef):
    description: str | None = None


class HintProfile(HintItem):
    base_skills: list[HintRef] = Field(default_factory=list)
    base_tools: list[HintRef] = Field(default_factory=list)


class HintGap(BaseModel):
    kind: GapKind
    name: str
    description: str = ""
    reason: str = ""


class HintResponse(BaseModel):
    agent_profile: HintProfile | None = None
    skills: list[HintItem] = Field(default_factory=list)
    tools: list[HintItem] = Field(default_factory=list)
    knowledge_packs: list[HintItem] = Field(default_factory=list)
    gaps: list[HintGap] = Field(default_factory=list)
    generated_skill: SkillDraftResult | None = None
    reasoning: str = ""