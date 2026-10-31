from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.sql import func

from src.catalog.hint.skill_markdown import skill_file_hash
from src.db.db_connection import Base
from src.db.enums.skill_visibility import SkillVisibility


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint(
            "(visibility = 'global') = (owner_id IS NULL)",
            name="owner_matches_visibility",
        ),
        Index(
            "uq_skills_global_name",
            "skill_name",
            unique=True,
            postgresql_where=text("owner_id IS NULL"),
        ),
        Index(
            "uq_skills_owner_name",
            "owner_id",
            "skill_name",
            unique=True,
            postgresql_where=text("owner_id IS NOT NULL"),
        ),
        Index("ix_skills_visibility_archived", "visibility", "archived_at"),
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

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    visibility: Mapped[SkillVisibility] = mapped_column(
        Enum(
            SkillVisibility,
            name="skill_visibility",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=SkillVisibility.PRIVATE,
        server_default=SkillVisibility.GLOBAL.value,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="",
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="",
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    skill_selected_freq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    domains: Mapped[list["KnowledgeDomain"]] = relationship(
        secondary="skill_domains",
        back_populates="skills",
        lazy="selectin",
        passive_deletes=True,
    )

    config_bundles: Mapped[list["ConfigBundle"]] = relationship(
        secondary="config_bundle_skills",
        back_populates="skills",
        lazy="raise",
        passive_deletes=True,
    )

    agent_profiles: Mapped[list["AgentProfile"]] = relationship(
        secondary="agent_profile_skills",
        back_populates="skills",
        lazy="raise",
        passive_deletes=True,
    )

    @validates("skill_name", "description", "content")
    def _sync_content_hash(self, key: str, value: str) -> str:
        fields = {
            "skill_name": self.skill_name or "",
            "description": self.description or "",
            "content": self.content or "",
        }
        fields[key] = value or ""
        self.content_hash = skill_file_hash(
            fields["skill_name"], fields["description"], fields["content"]
        )
        return value

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def __repr__(self):
        return f"<Skill id={self.id} name={self.skill_name} visibility={self.visibility}>"