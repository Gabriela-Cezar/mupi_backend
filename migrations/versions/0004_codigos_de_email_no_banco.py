"""Códigos de verificação e de recuperação guardados no banco (FAL-13).

Antes ficavam na memória do servidor: reiniciar apagava os códigos pendentes
e, com mais de um processo, um processo não via o código gerado pelo outro.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'email_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('purpose', sa.String(length=20), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('verificacao', 'recuperacao')",
            name='ck_email_codes_purpose',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('email_codes_pkey')),
        sa.UniqueConstraint('email', 'purpose', name=op.f('email_codes_email_key')),
    )
    with op.batch_alter_table('email_codes') as batch_op:
        batch_op.create_index(batch_op.f('ix_email_codes_expires_at'), ['expires_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('email_codes') as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_codes_expires_at'))

    op.drop_table('email_codes')
