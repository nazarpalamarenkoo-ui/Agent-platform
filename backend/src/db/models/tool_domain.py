from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base


class ToolDomain(Base):
    __tablename__ = "tool_domains"

    tool_id: Mapped[int] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"),
        primary_key=True,
    )
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_domains.id", ondelete="CASCADE"),
        primary_key=True,
    )


Index("ix_tool_domains_domain_id", ToolDomain.domain_id)