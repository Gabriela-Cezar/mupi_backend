"""Exclusões não apagam mais o histórico dos usuários (FAL-11).

Antes, excluir um ponto apagava (CASCADE) as visitas de todos os usuários a
ele, e excluir uma insígnia apagava a conquista de todos que a tinham.
Agora o banco recusa (RESTRICT) essas exclusões: o caminho é desativar.

Continuam em CASCADE, de propósito:
- `user_id` das duas tabelas: excluir a conta de um usuário apaga o
  histórico dele mesmo;
- `mupi_object_badges`: é só a ligação entre ponto e insígnia, não é
  histórico de ninguém.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabela, nome da restrição, coluna, tabela referenciada)
CHAVES = [
    ('user_visits', 'user_visits_object_id_fkey', 'object_id', 'mupi_objects'),
    ('user_badges', 'user_badges_badge_id_fkey', 'badge_id', 'badges'),
]


def _trocar_ondelete(ondelete: str) -> None:
    for tabela, nome, coluna, referenciada in CHAVES:
        # batch: no SQLite a tabela é recriada; no PostgreSQL vira ALTER TABLE
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.drop_constraint(nome, type_='foreignkey')
            batch_op.create_foreign_key(
                nome, referenciada, [coluna], ['id'], ondelete=ondelete,
            )


def upgrade() -> None:
    _trocar_ondelete('RESTRICT')


def downgrade() -> None:
    _trocar_ondelete('CASCADE')
