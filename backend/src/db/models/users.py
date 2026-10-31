from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum, Index, String, DateTime, Integer, text
from datetime import datetime
from src.db.db_connection import Base
from src.db.enums.user_role import UserRole
from sqlalchemy.sql import func


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_single_super_admin",
            "role",
            unique=True,
            postgresql_where=text("role = 'super_admin'"),
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        nullable=False,
        index=True,
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    token_limit: Mapped[int] = mapped_column(
        Integer,
        default=100_000,
        nullable=False
    )
    tokens_used: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    configs: Mapped[list["ConfigBundle"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        passive_deletes=True
    )

    token_usage_events: Mapped[list["TokenUsageEvent"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        passive_deletes=True
    )

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    def __repr__(self):
        return f"<User id={self.id} username={self.username} role={self.role}>"