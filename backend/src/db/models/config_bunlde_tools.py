from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base


class ConfigBundleTool(Base):
    __tablename__ = "config_bundle_tools"

    config_bundle_id: Mapped[int] = mapped_column(
        ForeignKey("config_bundles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tool_id: Mapped[int] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"),
        primary_key=True,
    )


Index("ix_config_bundle_tools_tool_id", ConfigBundleTool.tool_id)