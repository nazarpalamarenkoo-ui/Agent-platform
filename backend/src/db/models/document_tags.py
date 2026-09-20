from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base


class DocumentTag(Base):
    __tablename__ = "document_tags"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True,
    )


Index("ix_document_tags_tag_id", DocumentTag.tag_id)