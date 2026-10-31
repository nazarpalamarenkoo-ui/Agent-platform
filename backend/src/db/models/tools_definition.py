from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.db.db_connection import Base
from src.db.enums.tool_auth_type import ToolAuthType
from src.db.enums.tool_visibility import ToolVisibility


class ToolDefinition(Base):

    __tablename__ = "tools"
    __table_args__ = (
        CheckConstraint(
            "(visibility = 'global') = (owner_id IS NULL)",
            name="tool_owner_matches_visibility",
        ),
        Index(
            "uq_tools_global_name",
            "tool_name",
            unique=True,
            postgresql_where=text("owner_id IS NULL"),
        ),
        Index(
            "uq_tools_owner_name",
            "owner_id",
            "tool_name",
            unique=True,
            postgresql_where=text("owner_id IS NOT NULL"),
        ),
        Index("ix_tools_visibility_archived", "visibility", "archived_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    tool_name: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    visibility: Mapped[ToolVisibility] = mapped_column(
        Enum(
            ToolVisibility,
            name="tool_visibility",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ToolVisibility.GLOBAL,
        server_default=ToolVisibility.GLOBAL.value,
    )

    auth_type: Mapped[ToolAuthType] = mapped_column(
        Enum(
            ToolAuthType,
            name="tool_auth_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ToolAuthType.NONE,
        server_default=ToolAuthType.NONE.value,
    )

    auth_description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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

    tool_selected_freq: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    domains: Mapped[list["KnowledgeDomain"]] = relationship(
        secondary="tool_domains",
        back_populates="tools",
        lazy="selectin",
        passive_deletes=True,
    )

    config_bundles: Mapped[list["ConfigBundle"]] = relationship(
        secondary="config_bundle_tools",
        back_populates="tools",
        lazy="raise",
        passive_deletes=True,
    )

    agent_profiles: Mapped[list["AgentProfile"]] = relationship(
        secondary="agent_profile_tools",
        back_populates="tools",
        lazy="raise",
        passive_deletes=True,
    )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_custom(self) -> bool:
        return self.owner_id is not None

    def __repr__(self):
        return f"<ToolDefinition id={self.id} name={self.tool_name}>"