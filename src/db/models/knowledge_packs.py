from datetime import datetime

from sqlalchemy import String, ForeignKey, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.db.db_connection import Base


class KnowledgePack(Base):
    __tablename__ = "knowledge_packs"

    __table_args__ = (
        UniqueConstraint("domain_id", "name", name="uq_knowledge_pack_domain_name"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    slug: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    domain_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_domains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    description: Mapped[str] = mapped_column(String(255), nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    domain: Mapped["KnowledgeDomain"] = relationship(
        back_populates="knowledge_packs",
        lazy="selectin",
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="knowledge_pack",
        lazy="selectin",
    )

    config_bundles: Mapped[list["ConfigBundle"]] = relationship(
        secondary="config_bundle_knowledge_packs",
        back_populates="knowledge_packs",
        lazy="selectin",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<KnowledgePack id={self.id} slug={self.slug}>"