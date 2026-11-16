"""Posição e precisão do GPS na visita (VIS-03).

Acrescenta latitude, longitude e accuracy (metros) em user_visits. As visitas
já existentes ficam com os três campos nulos.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('user_visits') as batch_op:
        batch_op.add_column(sa.Column('latitude', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('longitude', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('accuracy', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('user_visits') as batch_op:
        batch_op.drop_column('accuracy')
        batch_op.drop_column('longitude')
        batch_op.drop_column('latitude')
