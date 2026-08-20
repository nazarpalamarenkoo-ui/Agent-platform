from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.db_connection import Base


class ToolDefinition(Base):
    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    tool_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_domains.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    domain: Mapped["KnowledgeDomain | None"] = relationship(lazy="selectin")

    tool_selected_freq: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    config_bundles: Mapped[list["ConfigBundle"]] = relationship(
        secondary="config_bundle_tools",
        back_populates="tools",
        lazy="selectin",
        passive_deletes=True,
    )

    agent_profiles: Mapped[list["AgentProfile"]] = relationship(
        secondary="agent_profile_tools",
        back_populates="tools",
        lazy="selectin",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<ToolDefinition id={self.id} name={self.tool_name}>"