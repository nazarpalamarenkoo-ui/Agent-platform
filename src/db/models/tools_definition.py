from sqlalchemy import Integer, String
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

    tool_selected_freq: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    config_bundles: Mapped[list["ConfigBundle"]] = relationship(
        secondary="config_bundle_tools",
        back_populates="tools",
    )

    agent_profiles: Mapped[list["AgentProfile"]] = relationship(
        secondary="agent_profile_tools",
        back_populates="tools",
    )

    def __repr__(self):
        return f"<ToolDefinition id={self.id} name={self.tool_name}>"