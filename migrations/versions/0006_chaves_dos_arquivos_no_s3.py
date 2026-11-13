"""Chaves dos arquivos no S3: mupi_objects.photo_key e badges.image_key (INF-04).

Primeira parte da mudança das imagens para o S3. Depois desta migração:

    python -m app.scripts.move_images_to_s3

copia as imagens guardadas no banco para o bucket e preenche as chaves. Só
então a 0007 apaga as colunas antigas (ela se recusa a rodar antes disso).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('mupi_objects') as batch_op:
        batch_op.add_column(sa.Column('photo_key', sa.String(length=300), nullable=True))

    with op.batch_alter_table('badges') as batch_op:
        batch_op.add_column(sa.Column('image_key', sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('badges') as batch_op:
        batch_op.drop_column('image_key')

    with op.batch_alter_table('mupi_objects') as batch_op:
        batch_op.drop_column('photo_key')
