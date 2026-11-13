"""Remove as imagens guardadas no banco (INF-04).

Segunda parte da mudança para o S3. Apaga:
- badges.image e badges.image_mime_type;
- as linhas de imagem de mupi_object_media e as colunas data e mime_type
  (a tabela passa a guardar só os links de vídeo; url vira obrigatória).

Recusa rodar se alguma imagem ainda não foi copiada para o S3 pelo script
`python -m app.scripts.move_images_to_s3`. Um ponto com várias imagens fica só
com a primeira (PT-05: uma foto por ponto); as outras são apagadas.

Desfazer recria as colunas vazias: as imagens não voltam para o banco
(continuam no S3).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PONTOS_SEM_COPIA = """
    SELECT COUNT(DISTINCT m.object_id)
    FROM mupi_object_media m
    JOIN mupi_objects o ON o.id = m.object_id
    WHERE m.type = 'image' AND m.data IS NOT NULL AND o.photo_key IS NULL
"""

INSIGNIAS_SEM_COPIA = """
    SELECT COUNT(*) FROM badges WHERE image IS NOT NULL AND image_key IS NULL
"""


def upgrade() -> None:
    conn = op.get_bind()

    pontos = conn.execute(sa.text(PONTOS_SEM_COPIA)).scalar()
    insignias = conn.execute(sa.text(INSIGNIAS_SEM_COPIA)).scalar()

    if pontos or insignias:
        raise RuntimeError(
            f"{pontos} ponto(s) e {insignias} insígnia(s) ainda têm imagem só no banco. "
            "Rode antes: python -m app.scripts.move_images_to_s3"
        )

    op.execute("DELETE FROM mupi_object_media WHERE type = 'image'")

    with op.batch_alter_table('mupi_object_media') as batch_op:
        batch_op.drop_constraint('ck_mupi_object_media_data_xor_url', type_='check')
        batch_op.drop_column('data')
        batch_op.drop_column('mime_type')
        batch_op.alter_column('url', existing_type=sa.String(length=500), nullable=False)

    with op.batch_alter_table('badges') as batch_op:
        batch_op.drop_column('image')
        batch_op.drop_column('image_mime_type')


def downgrade() -> None:
    with op.batch_alter_table('badges') as batch_op:
        batch_op.add_column(sa.Column('image_mime_type', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('image', sa.LargeBinary(), nullable=True))

    with op.batch_alter_table('mupi_object_media') as batch_op:
        batch_op.alter_column('url', existing_type=sa.String(length=500), nullable=True)
        batch_op.add_column(sa.Column('mime_type', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('data', sa.LargeBinary(), nullable=True))
        batch_op.create_check_constraint(
            'ck_mupi_object_media_data_xor_url',
            '(data IS NOT NULL) <> (url IS NOT NULL)',
        )
