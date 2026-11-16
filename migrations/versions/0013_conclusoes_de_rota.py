"""Conclusões de rota (ROT-04, ROT-08): user_route_completions.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_route_completions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='user_route_completions_user_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['route_id'], ['routes.id'], name='user_route_completions_route_id_fkey', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='user_route_completions_pkey'),
    )
    op.create_index('ix_user_route_completions_user_route', 'user_route_completions', ['user_id', 'route_id'])
    op.create_index('ix_user_route_completions_route_id', 'user_route_completions', ['route_id'])


def downgrade() -> None:
    op.drop_index('ix_user_route_completions_route_id', table_name='user_route_completions')
    op.drop_index('ix_user_route_completions_user_route', table_name='user_route_completions')
    op.drop_table('user_route_completions')
