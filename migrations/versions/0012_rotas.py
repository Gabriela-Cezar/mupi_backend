"""Rotas (ROT-01, ROT-02, ROT-03): rotas, pontos em ordem e temas.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'routes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('cover_key', sa.String(length=300), nullable=True),
        sa.Column('difficulty', sa.String(length=10), nullable=False),
        sa.Column('age_rating', sa.String(length=10), nullable=False),
        sa.Column('active', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('path', sa.JSON(), nullable=True),
        sa.Column('waypoints', sa.JSON(), nullable=True),
        sa.Column('distance_m', sa.Float(), nullable=True),
        sa.Column('walk_seconds', sa.Integer(), nullable=True),
        sa.Column('path_error', sa.Text(), nullable=True),
        sa.Column('path_computed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('estimated_minutes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            'estimated_minutes IS NULL OR estimated_minutes >= 1',
            name='ck_routes_estimated_minutes',
        ),
        sa.PrimaryKeyConstraint('id', name='routes_pkey'),
        sa.UniqueConstraint('name', name='routes_name_key'),
    )

    op.create_table(
        'route_points',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['route_id'], ['routes.id'], name='route_points_route_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name='route_points_object_id_fkey', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='route_points_pkey'),
        sa.UniqueConstraint('route_id', 'position', name='uq_route_points_route_position'),
        sa.UniqueConstraint('route_id', 'object_id', name='uq_route_points_route_object'),
    )
    op.create_index('ix_route_points_object_id', 'route_points', ['object_id'])

    op.create_table(
        'route_themes',
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('theme_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['route_id'], ['routes.id'], name='route_themes_route_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], name='route_themes_theme_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('route_id', 'theme_id', name='route_themes_pkey'),
    )
    op.create_index('ix_route_themes_theme_id', 'route_themes', ['theme_id'])


def downgrade() -> None:
    op.drop_index('ix_route_themes_theme_id', table_name='route_themes')
    op.drop_table('route_themes')
    op.drop_index('ix_route_points_object_id', table_name='route_points')
    op.drop_table('route_points')
    op.drop_table('routes')
