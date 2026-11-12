"""Versão da sessão do usuário: users.token_version (USR-05).

Os tokens do app passam a carregar essa versão em vez da "impressão digital"
da senha. Somar 1 cancela todas as sessões do usuário, com ou sem senha.

Ao aplicar, os tokens antigos (sem a versão) deixam de valer: cada usuário
entra de novo uma vez.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(
            sa.Column('token_version', sa.Integer(), server_default='0', nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('token_version')
