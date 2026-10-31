import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.db_connection import Base


class JobType(str, enum.Enum):
    DISCOVERY_INGEST = "discovery_ingest"
    # Заготовки під RFC (етап 4 і сповіщення), поки не використовуються:
    SKILL_GENERATION = "skill_generation"
    NOTIFY_SKILL_ARCHIVED = "notify_skill_archived"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class BackgroundJob(Base):
    """
    Єдиний tracker фонових завдань (job_type розрізняє тип).
    Рядкові колонки замість PG-enum: новий job_type/status не потребує
    ALTER TYPE у міграції.
    """

    __tablename__ = "background_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(20),
        default=JobStatus.PENDING.value,
        server_default=JobStatus.PENDING.value,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_background_jobs_type_status", "job_type", "status"),
    )