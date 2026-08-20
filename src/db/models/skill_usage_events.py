from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from src.db.db_connection import Base


class SkillUsageEvent(Base):
    __tablename__ = "skill_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    config_bundle_id: Mapped[int | None] = mapped_column(
        ForeignKey("config_bundles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    skill: Mapped["Skill"] = relationship(lazy="selectin")
    config_bundle: Mapped["ConfigBundle | None"] = relationship(lazy="selectin")
    user: Mapped["User"] = relationship(lazy="selectin")

    def __repr__(self):
        return f"<SkillUsageEvent id={self.id} skill_id={self.skill_id} user_id={self.user_id}>"