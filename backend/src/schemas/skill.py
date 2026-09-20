from pydantic import BaseModel

class SkillCreate(BaseModel):
    skill_name: str
    description: str
    domain_ids: list[int] = []

class SkillRead(BaseModel):
    id: int
    skill_name: str
    description: str
    skill_selected_freq: int
    model_config = {"from_attributes": True}