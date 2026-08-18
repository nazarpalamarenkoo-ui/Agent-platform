from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, Integer
from datetime import datetime
from src.db.db_connection import Base
from sqlalchemy.sql import func


class User(Base):
    __tablename__ = "users"

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
    )
    
    token_usage_events: Mapped[list["TokenUsageEvent"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self):
        return f"<User id={self.id} username={self.username}>"