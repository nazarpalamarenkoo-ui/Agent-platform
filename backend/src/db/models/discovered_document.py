from datetime import datetime
from sqlalchemy import String, Text, Float, DateTime, func, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.db.db_connection import Base
from src.db.enums.discovery_type import DiscoveredDocumentDecision

class DiscoveredDocument(Base):
    __tablename__ = "discovered_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    decision: Mapped[DiscoveredDocumentDecision] = mapped_column(
        SAEnum(DiscoveredDocumentDecision, name="discovered_document_decision"),
        nullable=False,
    )

    trust_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    educational_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    implementation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    authority_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    document_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )