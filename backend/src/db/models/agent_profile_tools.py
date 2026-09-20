from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base


class AgentProfileTool(Base):
    __tablename__ = "agent_profile_tools"

    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tool_id: Mapped[int] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"),
        primary_key=True,
    )


Index("ix_agent_profile_tools_tool_id", AgentProfileTool.tool_id)