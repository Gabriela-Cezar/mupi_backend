"""Novo modelo do ponto (PT-02, PT-03, PT-04, PT-07, PT-08, PT-09).

- Vários temas por ponto: tabela mupi_object_themes; o valor de
  mupi_objects.theme_id vira uma ligação e a coluna é removida.
- Blocos de texto: tabela mupi_object_sections; a description existente vira
  o bloco "Sobre o ponto" e a coluna é removida.
- Vídeos do YouTube: tabela mupi_object_videos, guardando só o ID do vídeo.
  Os links de mupi_object_media são convertidos; links que não são do YouTube
  são descartados (e listados na saída da migração). A tabela
  mupi_object_media é removida.
- Novas colunas do ponto: standalone ("existe individualmente", padrão sim),
  address, opening_hours e accessibility.

Desfazer recria as colunas e a tabela antigas: o primeiro tema (por nome)
volta para theme_id, os blocos são juntados na description e os vídeos voltam
como links youtube.com/watch?v=ID.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.youtube import extract_youtube_id, watch_url

revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TITULO_DA_DESCRICAO = "Sobre o ponto"


def upgrade() -> None:
    conn = op.get_bind()

    # ---------- Tabelas novas ----------
    op.create_table(
        'mupi_object_themes',
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('theme_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name='mupi_object_themes_object_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], name='mupi_object_themes_theme_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('object_id', 'theme_id', name='mupi_object_themes_pkey'),
    )
    op.create_index('ix_mupi_object_themes_theme_id', 'mupi_object_themes', ['theme_id'])

    op.create_table(
        'mupi_object_sections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name='mupi_object_sections_object_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='mupi_object_sections_pkey'),
        sa.UniqueConstraint('object_id', 'position', name='uq_mupi_object_sections_object_position'),
    )
    op.create_index('ix_mupi_object_sections_object_id', 'mupi_object_sections', ['object_id'])

    op.create_table(
        'mupi_object_videos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('youtube_id', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=True),
        sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name='mupi_object_videos_object_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='mupi_object_videos_pkey'),
        sa.UniqueConstraint('object_id', 'position', name='uq_mupi_object_videos_object_position'),
    )
    op.create_index('ix_mupi_object_videos_object_id', 'mupi_object_videos', ['object_id'])

    # ---------- Dados existentes ----------
    conn.execute(sa.text(
        "INSERT INTO mupi_object_themes (object_id, theme_id) "
        "SELECT id, theme_id FROM mupi_objects WHERE theme_id IS NOT NULL"
    ))

    descricoes = conn.execute(sa.text(
        "SELECT id, description FROM mupi_objects WHERE description IS NOT NULL"
    )).all()

    for object_id, description in descricoes:
        if description.strip():
            conn.execute(
                sa.text(
                    "INSERT INTO mupi_object_sections (object_id, position, title, body) "
                    "VALUES (:object_id, 0, :title, :body)"
                ),
                {"object_id": object_id, "title": TITULO_DA_DESCRICAO, "body": description.strip()},
            )

    videos = conn.execute(sa.text(
        "SELECT id, object_id, url, title FROM mupi_object_media "
        "WHERE type = 'video' ORDER BY object_id, id"
    )).all()

    proxima_posicao: dict[int, int] = {}

    for media_id, object_id, url, title in videos:
        youtube_id = extract_youtube_id(url)

        if youtube_id is None:
            print(f"Ponto {object_id}: vídeo {media_id} descartado (não é do YouTube): {url}")
            continue

        posicao = proxima_posicao.get(object_id, 0)
        proxima_posicao[object_id] = posicao + 1

        conn.execute(
            sa.text(
                "INSERT INTO mupi_object_videos (object_id, position, youtube_id, title) "
                "VALUES (:object_id, :position, :youtube_id, :title)"
            ),
            {"object_id": object_id, "position": posicao, "youtube_id": youtube_id, "title": title},
        )

    # ---------- Remove o que foi substituído ----------
    with op.batch_alter_table('mupi_object_media') as batch_op:
        batch_op.drop_index('ix_mupi_object_media_object_id')
        batch_op.drop_index('ix_mupi_object_media_id')

    op.drop_table('mupi_object_media')
    sa.Enum(name='media_type').drop(conn, checkfirst=True)

    with op.batch_alter_table('mupi_objects') as batch_op:
        batch_op.drop_index('ix_mupi_objects_theme_id')
        batch_op.drop_constraint('mupi_objects_theme_id_fkey', type_='foreignkey')
        batch_op.drop_column('theme_id')
        batch_op.drop_column('description')
        batch_op.add_column(sa.Column('standalone', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('address', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('opening_hours', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('accessibility', sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table('mupi_objects') as batch_op:
        batch_op.drop_column('accessibility')
        batch_op.drop_column('opening_hours')
        batch_op.drop_column('address')
        batch_op.drop_column('standalone')
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('theme_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'mupi_objects_theme_id_fkey', 'themes', ['theme_id'], ['id'], ondelete='SET NULL'
        )
        batch_op.create_index('ix_mupi_objects_theme_id', ['theme_id'], unique=False)

    op.create_table(
        'mupi_object_media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum('image', 'video', name='media_type'), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name='mupi_object_media_object_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='mupi_object_media_pkey'),
    )

    with op.batch_alter_table('mupi_object_media') as batch_op:
        batch_op.create_index('ix_mupi_object_media_id', ['id'], unique=False)
        batch_op.create_index('ix_mupi_object_media_object_id', ['object_id'], unique=False)

    # Primeiro tema (por nome) volta para theme_id
    conn.execute(sa.text(
        "UPDATE mupi_objects SET theme_id = ("
        " SELECT l.theme_id FROM mupi_object_themes l JOIN themes t ON t.id = l.theme_id"
        " WHERE l.object_id = mupi_objects.id ORDER BY t.name LIMIT 1)"
    ))

    # Blocos juntados na description
    blocos = conn.execute(sa.text(
        "SELECT object_id, title, body FROM mupi_object_sections ORDER BY object_id, position"
    )).all()

    textos: dict[int, list[str]] = {}
    for object_id, title, body in blocos:
        partes = textos.setdefault(object_id, [])
        partes.append(body if title == TITULO_DA_DESCRICAO else f"{title}\n\n{body}")

    for object_id, partes in textos.items():
        conn.execute(
            sa.text("UPDATE mupi_objects SET description = :description WHERE id = :id"),
            {"description": "\n\n".join(partes), "id": object_id},
        )

    videos = conn.execute(sa.text(
        "SELECT object_id, youtube_id, title FROM mupi_object_videos ORDER BY object_id, position"
    )).all()

    for object_id, youtube_id, title in videos:
        conn.execute(
            sa.text(
                "INSERT INTO mupi_object_media (object_id, type, url, title) "
                "VALUES (:object_id, 'video', :url, :title)"
            ),
            {"object_id": object_id, "url": watch_url(youtube_id), "title": title},
        )

    op.drop_index('ix_mupi_object_videos_object_id', table_name='mupi_object_videos')
    op.drop_table('mupi_object_videos')
    op.drop_index('ix_mupi_object_sections_object_id', table_name='mupi_object_sections')
    op.drop_table('mupi_object_sections')
    op.drop_index('ix_mupi_object_themes_theme_id', table_name='mupi_object_themes')
    op.drop_table('mupi_object_themes')
