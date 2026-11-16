"""Rota ativa do usuário (ROT-05 a ROT-10): user_active_routes.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_active_routes',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('next_index', sa.Integer(), server_default='0', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('cancelled_reason', sa.String(length=30), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='user_active_routes_user_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['route_id'], ['routes.id'], name='user_active_routes_route_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', name='user_active_routes_pkey'),
    )
    op.create_index('ix_user_active_routes_route_id', 'user_active_routes', ['route_id'])


def downgrade() -> None:
    op.drop_index('ix_user_active_routes_route_id', table_name='user_active_routes')
    op.drop_table('user_active_routes')
