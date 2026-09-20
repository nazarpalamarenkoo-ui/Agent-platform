"""add skill_domains table

Revision ID: 22b022e6e42b
Revises: 065c893213da
Create Date: 2026-08-31 16:38:23.854033
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "22b022e6e42b"
down_revision: Union[str, Sequence[str], None] = "065c893213da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _unique_exists(inspector, table: str, name: str) -> bool:
    return any(c["name"] == name for c in inspector.get_unique_constraints(table))


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if _unique_exists(inspector, "device_codes", "device_codes_device_code_key"):
        op.drop_constraint("device_codes_device_code_key", "device_codes", type_="unique")
    if not _unique_exists(inspector, "device_codes", "uq_device_codes_device_code"):
        op.create_unique_constraint("uq_device_codes_device_code", "device_codes", ["device_code"])

    if _unique_exists(inspector, "document_chunks", "document_chunks_qdrant_point_id_key"):
        op.drop_constraint("document_chunks_qdrant_point_id_key", "document_chunks", type_="unique")
    if not _unique_exists(inspector, "document_chunks", "uq_document_chunks_qdrant_point_id"):
        op.create_unique_constraint("uq_document_chunks_qdrant_point_id", "document_chunks", ["qdrant_point_id"])

    if _unique_exists(inspector, "tools", "tools_tool_name_key"):
        op.drop_constraint("tools_tool_name_key", "tools", type_="unique")
    if not _unique_exists(inspector, "tools", "uq_tools_tool_name"):
        op.create_unique_constraint("uq_tools_tool_name", "tools", ["tool_name"])

    if _unique_exists(inspector, "users", "users_email_key"):
        op.drop_constraint("users_email_key", "users", type_="unique")
    if _unique_exists(inspector, "users", "users_username_key"):
        op.drop_constraint("users_username_key", "users", type_="unique")

    if not _unique_exists(inspector, "users", "uq_users_email"):
        op.create_unique_constraint("uq_users_email", "users", ["email"])
    if not _unique_exists(inspector, "users", "uq_users_username"):
        op.create_unique_constraint("uq_users_username", "users", ["username"])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if _unique_exists(inspector, "users", "uq_users_username"):
        op.drop_constraint("uq_users_username", "users", type_="unique")
    if _unique_exists(inspector, "users", "uq_users_email"):
        op.drop_constraint("uq_users_email", "users", type_="unique")

    if not _unique_exists(inspector, "users", "users_username_key"):
        op.create_unique_constraint("users_username_key", "users", ["username"])
    if not _unique_exists(inspector, "users", "users_email_key"):
        op.create_unique_constraint("users_email_key", "users", ["email"])

    if _unique_exists(inspector, "tools", "uq_tools_tool_name"):
        op.drop_constraint("uq_tools_tool_name", "tools", type_="unique")
    if not _unique_exists(inspector, "tools", "tools_tool_name_key"):
        op.create_unique_constraint("tools_tool_name_key", "tools", ["tool_name"])

    if _unique_exists(inspector, "document_chunks", "uq_document_chunks_qdrant_point_id"):
        op.drop_constraint("uq_document_chunks_qdrant_point_id", "document_chunks", type_="unique")
    if not _unique_exists(inspector, "document_chunks", "document_chunks_qdrant_point_id_key"):
        op.create_unique_constraint("document_chunks_qdrant_point_id_key", "document_chunks", ["qdrant_point_id"])

    if _unique_exists(inspector, "device_codes", "uq_device_codes_device_code"):
        op.drop_constraint("uq_device_codes_device_code", "device_codes", type_="unique")
    if not _unique_exists(inspector, "device_codes", "device_codes_device_code_key"):
        op.create_unique_constraint("device_codes_device_code_key", "device_codes", ["device_code"])