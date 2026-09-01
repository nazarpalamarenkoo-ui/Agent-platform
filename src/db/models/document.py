from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DateTime, Enum, UniqueConstraint, ForeignKey
from sqlalchemy.sql import func

from src.db.db_connection import Base
from src.db.enums.document_status import DocumentStatus
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source", "content_hash", "version", name="uq_document_source_hash_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)

    domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_domains.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    domain: Mapped["KnowledgeDomain | None"] = relationship(lazy="selectin")

    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"), nullable=False,
    )

    size: Mapped[int] = mapped_column(Integer, nullable=False)

    tags: Mapped[list["Tag"]] = relationship(
        secondary="document_tags", back_populates="documents", lazy="selectin", passive_deletes=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus), nullable=False, default=DocumentStatus.PENDING)
    embedding_model: Mapped[str] = mapped_column(String(150), nullable=False)
    embedding_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    knowledge_type: Mapped[KnowledgeType] = mapped_column(Enum(KnowledgeType, name="knowledge_type"), nullable=False)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True,
    )