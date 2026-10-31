"""update tools and add skill access logs models

Revision ID: 2a97d3c433bb
Revises: bf2217219684
Create Date: 2026-10-14 12:53:42.116607

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '2a97d3c433bb'
down_revision: Union[str, Sequence[str], None] = 'bf2217219684'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

tool_visibility = postgresql.ENUM('global', 'private', name='tool_visibility')
tool_visibility_col = postgresql.ENUM(
    'global', 'private', name='tool_visibility', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    tool_visibility.create(op.get_bind(), checkfirst=True)

    op.create_table('skill_access_logs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=True),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['users.id'], name=op.f('fk_skill_access_logs_admin_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_skill_access_logs_owner_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], name=op.f('fk_skill_access_logs_skill_id_skills'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_skill_access_logs'))
    )
    op.create_index(op.f('ix_skill_access_logs_admin_id'), 'skill_access_logs', ['admin_id'], unique=False)
    op.create_index(op.f('ix_skill_access_logs_created_at'), 'skill_access_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_skill_access_logs_owner_id'), 'skill_access_logs', ['owner_id'], unique=False)

    op.add_column('tools', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.add_column('tools', sa.Column('visibility', tool_visibility_col, server_default='global', nullable=False))
    op.drop_constraint(op.f('uq_tools_tool_name'), 'tools', type_='unique')
    op.create_index(op.f('ix_tools_owner_id'), 'tools', ['owner_id'], unique=False)
    op.create_index(op.f('ix_tools_tool_name'), 'tools', ['tool_name'], unique=False)
    op.create_index('ix_tools_visibility_archived', 'tools', ['visibility', 'archived_at'], unique=False)
    op.create_index('uq_tools_global_name', 'tools', ['tool_name'], unique=True, postgresql_where=sa.text('owner_id IS NULL'))
    op.create_index('uq_tools_owner_name', 'tools', ['owner_id', 'tool_name'], unique=True, postgresql_where=sa.text('owner_id IS NOT NULL'))
    op.create_foreign_key(op.f('fk_tools_owner_id_users'), 'tools', 'users', ['owner_id'], ['id'], ondelete='CASCADE')
    op.create_check_constraint(op.f('ck_tools_tool_owner_matches_visibility'), 'tools', "(visibility = 'global') = (owner_id IS NULL)")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_tools_tool_owner_matches_visibility'), 'tools', type_='check')
    op.drop_constraint(op.f('fk_tools_owner_id_users'), 'tools', type_='foreignkey')
    op.drop_index('uq_tools_owner_name', table_name='tools', postgresql_where=sa.text('owner_id IS NOT NULL'))
    op.drop_index('uq_tools_global_name', table_name='tools', postgresql_where=sa.text('owner_id IS NULL'))
    op.drop_index('ix_tools_visibility_archived', table_name='tools')
    op.drop_index(op.f('ix_tools_tool_name'), table_name='tools')
    op.drop_index(op.f('ix_tools_owner_id'), table_name='tools')
    op.create_unique_constraint(op.f('uq_tools_tool_name'), 'tools', ['tool_name'])
    op.drop_column('tools', 'visibility')
    op.drop_column('tools', 'owner_id')
    tool_visibility.drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f('ix_skill_access_logs_owner_id'), table_name='skill_access_logs')
    op.drop_index(op.f('ix_skill_access_logs_created_at'), table_name='skill_access_logs')
    op.drop_index(op.f('ix_skill_access_logs_admin_id'), table_name='skill_access_logs')
    op.drop_table('skill_access_logs')