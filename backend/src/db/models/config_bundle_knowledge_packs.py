from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base


class ConfigBundleKnowledgePack(Base):
    __tablename__ = "config_bundle_knowledge_packs"

    config_bundle_id: Mapped[int] = mapped_column(
        ForeignKey("config_bundles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_pack_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_packs.id", ondelete="CASCADE"),
        primary_key=True,
    )


Index("ix_config_bundle_knowledge_packs_pack_id", ConfigBundleKnowledgePack.knowledge_pack_id)