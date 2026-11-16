"""Áudio do ponto (PT-06): chave do arquivo no S3 e duração em segundos.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('mupi_objects') as batch_op:
        batch_op.add_column(sa.Column('audio_key', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('audio_duration', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Os arquivos de áudio continuam no S3; só as referências saem do banco
    with op.batch_alter_table('mupi_objects') as batch_op:
        batch_op.drop_column('audio_duration')
        batch_op.drop_column('audio_key')
