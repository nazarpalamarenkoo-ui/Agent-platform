from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.db.db_connection import Base
from src.db.enums.notification_type import NotificationType


class Notification(Base):

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "uq_notifications_user_type_skill",
            "user_id",
            "type",
            "skill_id",
            unique=True,
            postgresql_where=text("skill_id IS NOT NULL"),
        ),
        Index(
            "uq_notifications_user_type_tool",
            "user_id",
            "type",
            "tool_id",
            unique=True,
            postgresql_where=text("tool_id IS NOT NULL"),
        ),
        Index("ix_notifications_user_read", "user_id", "read_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    type: Mapped[NotificationType] = mapped_column(
        Enum(
            NotificationType,
            name="notification_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=True,
    )

    tool_id: Mapped[int | None] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=True,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return f"<Notification id={self.id} user_id={self.user_id} type={self.type}>"