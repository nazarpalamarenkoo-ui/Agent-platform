from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base


class AgentProfileSkill(Base):
    __tablename__ = "agent_profile_skills"

    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )


Index("ix_agent_profile_skills_skill_id", AgentProfileSkill.skill_id)