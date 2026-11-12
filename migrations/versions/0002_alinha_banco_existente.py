"""Alinha o banco de desenvolvimento aos models (FAL-14).

O banco criado antes do Alembic tinha nomes antigos da época em que a tabela
`users` se chamava `usuarios`, e um tipo ENUM que sobrou de uma versão
antiga (`mediatype`, com IMAGE/VIDEO em maiúsculas; o usado é `media_type`).

Tudo aqui usa IF EXISTS: num banco criado pela 0001 nada acontece.
Só vale para PostgreSQL (o SQLite dos testes é sempre criado pela 0001).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return

    # Índices da tabela users com o nome antigo
    op.execute('ALTER INDEX IF EXISTS ix_usuarios_email RENAME TO ix_users_email')
    op.execute('ALTER INDEX IF EXISTS ix_usuarios_id RENAME TO ix_users_id')

    # Chave primária com o nome antigo (RENAME CONSTRAINT não tem IF EXISTS)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'usuarios_pkey'
                  AND conrelid = 'users'::regclass
            ) THEN
                ALTER TABLE users RENAME CONSTRAINT usuarios_pkey TO users_pkey;
            END IF;
        END
        $$
    """)

    # Tipo ENUM antigo, sem nenhuma coluna usando (se alguma usasse, o
    # PostgreSQL recusaria e a migração inteira seria desfeita)
    op.execute('DROP TYPE IF EXISTS mediatype')


def downgrade() -> None:
    # Não volta aos nomes antigos: eram um resto do passado, não um estado
    # que valha a pena reconstruir.
    pass
