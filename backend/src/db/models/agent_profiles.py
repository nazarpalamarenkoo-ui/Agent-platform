from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.db.db_connection import Base


class AgentProfile(Base):
    __tablename__ = "agent_profiles"
    __table_args__ = (
        Index(
            "uq_agent_profiles_single_neutral",
            "is_neutral",
            unique=True,
            postgresql_where=text("is_neutral"),
        ),
    )

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

    is_neutral: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
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

    skills: Mapped[list["Skill"]] = relationship(
        secondary="agent_profile_skills",
        back_populates="agent_profiles",
        lazy="selectin",
        passive_deletes=True,
    )

    tools: Mapped[list["ToolDefinition"]] = relationship(
        secondary="agent_profile_tools",
        back_populates="agent_profiles",
        lazy="selectin",
        passive_deletes=True,
    )

    config_bundles: Mapped[list["ConfigBundle"]] = relationship(
        back_populates="agent",
        lazy="raise",
        passive_deletes=True,
    )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def __repr__(self):
        return f"<AgentProfile id={self.id} name={self.agent_name}>"