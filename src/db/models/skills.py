from sqlalchemy import Integer, String, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.db_connection import Base


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("skill_name", "domain_id", name="uq_skill_name_domain"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    skill_name: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_domains.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    
    domain: Mapped["KnowledgeDomain"] = relationship(lazy="selectin")
    
    skill_selected_freq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    config_bundles: Mapped[list["ConfigBundle"]] = relationship(
        secondary="config_bundle_skills",
        back_populates="skills",
        lazy="selectin",
        passive_deletes=True,
    )

    agent_profiles: Mapped[list["AgentProfile"]] = relationship(
        secondary="agent_profile_skills",
        back_populates="skills",
        lazy="selectin",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Skill id={self.id} name={self.skill_name}>"