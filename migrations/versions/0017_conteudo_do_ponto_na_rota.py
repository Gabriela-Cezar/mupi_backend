"""Conteúdo próprio de um ponto dentro de uma rota.

Tabelas route_point_contents (nome, foto, áudio, informações do local),
route_point_sections (blocos de texto) e route_point_videos.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'route_point_contents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=True),
        sa.Column('photo_key', sa.String(length=300), nullable=True),
        sa.Column('audio_key', sa.String(length=300), nullable=True),
        sa.Column('audio_duration', sa.Integer(), nullable=True),
        sa.Column('address', sa.String(length=300), nullable=True),
        sa.Column('opening_hours', sa.Text(), nullable=True),
        sa.Column('accessibility', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['route_id'], ['routes.id'], name='route_point_contents_route_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name='route_point_contents_object_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='route_point_contents_pkey'),
        sa.UniqueConstraint('route_id', 'object_id', name='uq_route_point_contents_route_object'),
    )
    op.create_index('ix_route_point_contents_object_id', 'route_point_contents', ['object_id'])

    op.create_table(
        'route_point_sections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['content_id'], ['route_point_contents.id'], name='route_point_sections_content_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='route_point_sections_pkey'),
        sa.UniqueConstraint('content_id', 'position', name='uq_route_point_sections_content_position'),
    )
    op.create_index('ix_route_point_sections_content_id', 'route_point_sections', ['content_id'])

    op.create_table(
        'route_point_videos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('youtube_id', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=True),
        sa.ForeignKeyConstraint(['content_id'], ['route_point_contents.id'], name='route_point_videos_content_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='route_point_videos_pkey'),
        sa.UniqueConstraint('content_id', 'position', name='uq_route_point_videos_content_position'),
    )
    op.create_index('ix_route_point_videos_content_id', 'route_point_videos', ['content_id'])


def downgrade() -> None:
    op.drop_index('ix_route_point_videos_content_id', table_name='route_point_videos')
    op.drop_table('route_point_videos')
    op.drop_index('ix_route_point_sections_content_id', table_name='route_point_sections')
    op.drop_table('route_point_sections')
    op.drop_index('ix_route_point_contents_object_id', table_name='route_point_contents')
    op.drop_table('route_point_contents')
