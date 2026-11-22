from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base


class ConfigBundleAgent(Base):
    __tablename__ = "config_bundle_agents"

    config_bundle_id: Mapped[int] = mapped_column(
        ForeignKey("config_bundles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )


Index("ix_config_bundle_agents_agent_id", ConfigBundleAgent.agent_id)