from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.db_connection import Base


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    agent_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    skills: Mapped[list["Skill"]] = relationship(
        secondary="agent_profile_skills",
        back_populates="agent_profiles",
    )
    
    tools: Mapped[list["ToolDefinition"]] = relationship(
        secondary="agent_profile_tools",
        back_populates="agent_profiles",
    )

    config_bundles: Mapped[list["ConfigBundle"]] = relationship(
        back_populates="agent",
    )
 
    def __repr__(self):
        return f"<AgentProfile id={self.id} name={self.agent_name}>"