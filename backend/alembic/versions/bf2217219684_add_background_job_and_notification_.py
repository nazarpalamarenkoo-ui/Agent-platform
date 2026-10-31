"""add background_job and notification tables

Revision ID: bf2217219684
Revises: d023accfcc76
Create Date: 2026-10-07 16:44:52.609104

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "bf2217219684"
down_revision: Union[str, Sequence[str], None] = "d023accfcc76"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()

    # The ENUM may already exist (for example, if it was created by a
    # previous migration). checkfirst=True prevents a duplicate CREATE TYPE.
    notification_type = postgresql.ENUM(
        "skill_archived",
        "tool_archived",
        name="notification_type",
        create_type=False,
    )
    notification_type.create(bind, checkfirst=True)

    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_background_jobs_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_background_jobs"),
        ),
    )

    op.create_index(
        "ix_background_jobs_type_status",
        "background_jobs",
        ["job_type", "status"],
        unique=False,
    )

    op.create_table(
        "notifications",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "type",
            notification_type,
            nullable=False,
        ),
        sa.Column(
            "skill_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "tool_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_notifications_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id"],
            ["tools.id"],
            name=op.f("fk_notifications_tool_id_tools"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_notifications"),
        ),
    )

    op.create_index(
        "ix_notifications_user_read",
        "notifications",
        ["user_id", "read_at"],
        unique=False,
    )

    op.create_index(
        "uq_notifications_user_type_skill",
        "notifications",
        ["user_id", "type", "skill_id"],
        unique=True,
        postgresql_where=sa.text("skill_id IS NOT NULL"),
    )

    op.create_index(
        "uq_notifications_user_type_tool",
        "notifications",
        ["user_id", "type", "tool_id"],
        unique=True,
        postgresql_where=sa.text("tool_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()

    op.drop_index(
        "uq_notifications_user_type_tool",
        table_name="notifications",
        postgresql_where=sa.text("tool_id IS NOT NULL"),
    )

    op.drop_index(
        "uq_notifications_user_type_skill",
        table_name="notifications",
        postgresql_where=sa.text("skill_id IS NOT NULL"),
    )

    op.drop_index(
        "ix_notifications_user_read",
        table_name="notifications",
    )

    op.drop_table("notifications")

    op.drop_index(
        "ix_background_jobs_type_status",
        table_name="background_jobs",
    )

    op.drop_table("background_jobs")

    notification_type = postgresql.ENUM(
        "skill_archived",
        "tool_archived",
        name="notification_type",
        create_type=False,
    )
    notification_type.drop(bind, checkfirst=True)
