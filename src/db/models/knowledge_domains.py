from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.db_connection import Base


class KnowledgeDomain(Base):
    __tablename__ = "knowledge_domains"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    parent_domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_domains.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    children: Mapped[list["KnowledgeDomain"]] = relationship(
        back_populates="parent",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    parent: Mapped["KnowledgeDomain | None"] = relationship(
        back_populates="children",
        remote_side=[id],
    )

    skills: Mapped[list["Skill"]] = relationship(
        back_populates="domain",
        lazy="selectin",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<KnowledgeDomain id={self.id} slug={self.slug}>"