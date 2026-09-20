from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base


class SkillDomain(Base):
    __tablename__ = "skill_domains"

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_domains.id", ondelete="CASCADE"),
        primary_key=True,
    )


Index("ix_skill_domains_domain_id", SkillDomain.domain_id)