from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base
from src.db.enums.device_code_status import DeviceStatus


class DeviceCode(Base):
    __tablename__ = "device_codes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    device_code: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(
            DeviceStatus,
            name="device_status",
        ),
        nullable=False,
        default=DeviceStatus.PENDING,
    )
    scope: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    interval: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_device_codes_status_expires_at", "status", "expires_at"),
    )

    def __repr__(self):
        return (
            f"<DeviceCode(id={self.id}, device_code='{self.device_code}', "
            f"user_id={self.user_id}, scope='{self.scope}', "
            f"expires_at={self.expires_at}, interval={self.interval})>"
        )