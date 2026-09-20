# tags.py
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.db_connection import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tag_name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    documents: Mapped[list["Document"]] = relationship(
        secondary="document_tags",
        back_populates="tags",
        lazy="selectin",
        passive_deletes=True,
    )