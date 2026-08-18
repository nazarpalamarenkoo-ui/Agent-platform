from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, DateTime, UniqueConstraint, Integer
from datetime import datetime
from src.db.db_connection import Base
from sqlalchemy.sql import func


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
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
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

    user: Mapped["User"] = relationship(
        back_populates="configs",
    )

    skills: Mapped[list["Skill"]] = relationship(
        secondary="config_bundle_skills",
        back_populates="config_bundles",
    )

    tools: Mapped[list["ToolDefinition"]] = relationship(
        secondary="config_bundle_tools",
        back_populates="config_bundles",
    )

    def __repr__(self):
        return f"<ConfigBundle id={self.id} name={self.name}>"