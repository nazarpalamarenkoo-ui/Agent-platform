from enum import Enum

from pydantic import BaseModel, Field


class CandidateKind(str, Enum):
    PROFILE = "profile"
    SKILL = "skill"
    TOOL = "tool"
    PACK = "pack"


class GapKind(str, Enum):
    SKILL = "skill"
    TOOL = "tool"
    PACK = "pack"


class CatalogCandidate(BaseModel):
    key: str
    kind: CandidateKind
    entity_id: int
    name: str
    description: str

    @staticmethod
    def build_key(kind: CandidateKind, entity_id: int) -> str:
        return f"{kind.value}:{entity_id}"


class CatalogGap(BaseModel):
    kind: GapKind
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=255)
    reason: str = Field(default="", max_length=300)


class HintSelection(BaseModel):

    profile_key: str | None = None
    skill_keys: list[str] = Field(default_factory=list)
    tool_keys: list[str] = Field(default_factory=list)
    knowledge_pack_keys: list[str] = Field(default_factory=list)
    gaps: list[CatalogGap] = Field(default_factory=list)
    reasoning: str = ""


class HintProposal(BaseModel):
    agent_profile: dict | None = None
    skills: list[dict] = Field(default_factory=list)
    tools: list[dict] = Field(default_factory=list)
    knowledge_packs: list[dict] = Field(default_factory=list)
    gaps: list[CatalogGap] = Field(default_factory=list)
    reasoning: str = ""