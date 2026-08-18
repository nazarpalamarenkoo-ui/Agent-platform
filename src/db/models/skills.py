from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.db_connection import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    skill_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    skill_selected_freq: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    config_bundles: Mapped[list["ConfigBundle"]] = relationship(
        secondary="config_bundle_skills",
        back_populates="skills",
    )

    agent_profiles: Mapped[list["AgentProfile"]] = relationship(
        secondary="agent_profile_skills",
        back_populates="skills",
    )

    def __repr__(self):
        return f"<Skill id={self.id} name={self.skill_name}>"