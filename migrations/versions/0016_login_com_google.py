"""Login com Google (USR-04): users.google_sub e senha opcional.

A conta criada pelo Google não tem senha. Desfazer só é possível se todas as
contas tiverem senha (senão a migração para e avisa).

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('google_sub', sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint('users_google_sub_key', ['google_sub'])
        batch_op.alter_column(
            'password_hash', existing_type=sa.String(length=255), nullable=True
        )


def downgrade() -> None:
    sem_senha = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM users WHERE password_hash IS NULL")
    ).scalar()

    if sem_senha:
        raise RuntimeError(
            f"{sem_senha} conta(s) só com Google, sem senha: não dá para voltar "
            "a exigir senha. Exclua essas contas antes de desfazer a 0016."
        )

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'password_hash', existing_type=sa.String(length=255), nullable=False
        )
        batch_op.drop_constraint('users_google_sub_key', type_='unique')
        batch_op.drop_column('google_sub')
