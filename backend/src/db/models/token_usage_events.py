from src.db.db_connection import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy import Integer, ForeignKey, DateTime
from datetime import datetime

class TokenUsageEvent(Base):
    __tablename__ = "token_usage_events"

    id: Mapped[int] = mapped_column(
        Integer, 
        primary_key=True, 
        autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete='CASCADE'), 
        nullable=False, 
        index=True
    )
    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"), nullable=True,
    )
    tokens_used: Mapped[int] = mapped_column(
        Integer, 
        nullable=False
    )
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    user: Mapped["User"] = relationship(back_populates="token_usage_events", lazy="selectin", passive_deletes=True)