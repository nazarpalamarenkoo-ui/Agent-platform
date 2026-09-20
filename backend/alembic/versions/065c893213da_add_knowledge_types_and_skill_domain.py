"""add knowledge_types and skill_domain

Revision ID: 065c893213da
Revises: 00327087014f
Create Date: 2026-08-21 18:41:16.723128
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision: str = "065c893213da"
down_revision: Union[str, Sequence[str], None] = "00327087014f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


knowledge_type_enum = postgresql.ENUM(
    "PRINCIPLE", "REFERENCE", "EXAMPLE", name="knowledge_type"
)


def upgrade() -> None:
    """Upgrade schema."""
    knowledge_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column("documents", sa.Column("knowledge_type", knowledge_type_enum, nullable=False))

    op.drop_index(op.f("ix_skills_domain_id"), table_name="skills")
    op.drop_constraint("uq_skill_name_domain", "skills", type_="unique")
    op.create_unique_constraint("uq_skill_name", "skills", ["skill_name"])

    bind = op.get_bind()
    inspector = inspect(bind)

    skill_fks = {fk["name"] for fk in inspector.get_foreign_keys("skills") if fk.get("name")}

    if "skills_domain_id_fkey" in skill_fks:
        op.drop_constraint("skills_domain_id_fkey", "skills", type_="foreignkey")

    if "fk_skills_domain_id_knowledge_domains" in skill_fks:
        op.drop_constraint("fk_skills_domain_id_knowledge_domains", "skills", type_="foreignkey")

    op.drop_column("skills", "domain_id")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("skills", sa.Column("domain_id", sa.INTEGER(), nullable=False))
    op.create_foreign_key("fk_skills_domain_id_knowledge_domains", "skills", "knowledge_domains", ["domain_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint("uq_skill_name", "skills", type_="unique")
    op.create_unique_constraint("uq_skill_name_domain", "skills", ["skill_name", "domain_id"])
    op.create_index(op.f("ix_skills_domain_id"), "skills", ["domain_id"], unique=False)
    op.drop_column("documents", "knowledge_type")

    knowledge_type_enum.drop(op.get_bind(), checkfirst=True)