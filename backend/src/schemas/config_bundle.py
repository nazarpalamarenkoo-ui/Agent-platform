from pydantic import BaseModel, Field, model_validator
from src.schemas.agent import AgentRead, SkillRead, ToolRead
from src.schemas.knowledge_pack import KnowledgePackRead


class ConfigBundleCreate(BaseModel):
    agent_id: int | None = None
    agent_ids: list[int] = Field(default_factory=list)
    name: str
    description: str
    skill_ids: list[int] = Field(default_factory=list)
    tool_ids: list[int] = Field(default_factory=list)
    knowledge_pack_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_agents(self):
        combined: list[int] = []
        if self.agent_id is not None:
            combined.append(self.agent_id)
        for aid in self.agent_ids:
            if aid not in combined:
                combined.append(aid)
        if not combined:
            raise ValueError("At least one agent profile must be specified via 'agent_ids' or 'agent_id'")
        self.agent_ids = combined
        self.agent_id = combined[0]
        return self


class ConfigBundleFromAgent(BaseModel):
    agent_id: int | None = None
    agent_ids: list[int] = Field(default_factory=list)
    name: str
    description: str


class ConfigBundleClone(BaseModel):
    name: str
    description: str | None = None


class AgentProfileBriefRead(BaseModel):
    id: int
    agent_name: str
    description: str
    model_config = {"from_attributes": True}


class ConfigBundleRead(BaseModel):
    id: int
    user_id: int
    agent_id: int | None = None
    agent_profiles: list[AgentProfileBriefRead] = Field(default_factory=list)
    name: str
    description: str
    skills: list[SkillRead]
    tools: list[ToolRead]
    knowledge_packs: list[KnowledgePackRead]
    model_config = {"from_attributes": True}