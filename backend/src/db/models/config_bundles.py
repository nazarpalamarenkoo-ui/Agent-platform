from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.db.db_connection import Base


class ConfigBundle(Base):
    __tablename__ = "config_bundles"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "name",
            name="uq_config_bundle_user_name",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
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

    user: Mapped["User"] = relationship(
        back_populates="configs",
        lazy="selectin",
        passive_deletes=True,
    )

    agent: Mapped["AgentProfile"] = relationship(
        back_populates="config_bundles",
        lazy="selectin",
        passive_deletes=True,
    )

    skills: Mapped[list["Skill"]] = relationship(
        secondary="config_bundle_skills",
        back_populates="config_bundles",
        lazy="selectin",
        passive_deletes=True,
    )

    tools: Mapped[list["ToolDefinition"]] = relationship(
        secondary="config_bundle_tools",
        back_populates="config_bundles",
        lazy="selectin",
        passive_deletes=True,
    )

    knowledge_packs: Mapped[list["KnowledgePack"]] = relationship(
        secondary="config_bundle_knowledge_packs",
        back_populates="config_bundles",
        lazy="selectin",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<ConfigBundle id={self.id} name={self.name}>"