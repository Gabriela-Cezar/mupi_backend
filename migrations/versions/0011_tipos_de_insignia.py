"""Tipos de insígnia (INS-01): ponto na própria insígnia e insígnia ativa.

- A ligação insígnia ↔ ponto deixa de ser muitos-para-muitos
  (`mupi_object_badges`) e vira a coluna `badges.object_id`: a insígnia de
  visita é de exatamente um ponto.
- O tipo `manual` passa a se chamar `point_visit`.
- Nova coluna `badges.active` (todas começam ativas).

Conversão das insígnias manuais já cadastradas:
- ligada a um ponto: fica com ele;
- ligada a vários pontos: fica com o de menor id; os outros são listados na
  saída, para o administrador criar insígnias separadas se quiser;
- sem ponto e sem ninguém que a tenha conquistado: é apagada (ninguém
  conseguiria conquistá-la) e listada na saída;
- sem ponto, mas já conquistada: fica com o ponto onde foi conquistada mais
  vezes; se nem isso existir, a migração para e pede para ligar a insígnia
  a um ponto antes.

Desfazer recria `mupi_object_badges` a partir de `object_id`.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REGRA_NOVA = (
    "(rule_type = 'point_visit' AND object_id IS NOT NULL "
    "AND required_count IS NULL AND theme_id IS NULL) "
    "OR (rule_type = 'visit_count' AND required_count IS NOT NULL "
    "AND required_count >= 1 AND object_id IS NULL AND theme_id IS NULL) "
    "OR (rule_type = 'theme_visit_count' AND required_count IS NOT NULL "
    "AND required_count >= 1 AND theme_id IS NOT NULL AND object_id IS NULL)"
)

REGRA_ANTIGA = (
    "(rule_type = 'manual' AND required_count IS NULL "
    "AND theme_id IS NULL) "
    "OR (rule_type = 'visit_count' AND required_count >= 1 "
    "AND theme_id IS NULL) "
    "OR (rule_type = 'theme_visit_count' AND required_count >= 1 "
    "AND theme_id IS NOT NULL)"
)


def _ponto_de_cada_insignia(conn) -> dict[int, int]:
    """Escolhe o ponto de cada insígnia manual (ver a docstring do módulo)."""
    manuais = conn.execute(sa.text(
        "SELECT id, name FROM badges WHERE rule_type = 'manual' ORDER BY id"
    )).all()

    escolhido: dict[int, int] = {}
    sem_ponto: list[str] = []

    for badge_id, nome in manuais:
        pontos = [
            object_id for (object_id,) in conn.execute(
                sa.text(
                    "SELECT object_id FROM mupi_object_badges "
                    "WHERE badge_id = :b ORDER BY object_id"
                ),
                {"b": badge_id},
            )
        ]

        if pontos:
            escolhido[badge_id] = pontos[0]
            if len(pontos) > 1:
                print(
                    f"Insígnia {badge_id} ({nome}) estava em {len(pontos)} pontos; "
                    f"fica só com o ponto {pontos[0]}. Pontos que perderam a "
                    f"ligação: {', '.join(map(str, pontos[1:]))}"
                )
            continue

        # Sem ponto: usa onde ela foi conquistada, se foi
        onde = conn.execute(
            sa.text(
                "SELECT collected_at_object_id FROM user_badges "
                "WHERE badge_id = :b AND collected_at_object_id IS NOT NULL "
                "GROUP BY collected_at_object_id "
                "ORDER BY COUNT(*) DESC, collected_at_object_id LIMIT 1"
            ),
            {"b": badge_id},
        ).scalar()

        conquistada = conn.execute(
            sa.text("SELECT COUNT(*) FROM user_badges WHERE badge_id = :b"),
            {"b": badge_id},
        ).scalar()

        if onde is not None:
            escolhido[badge_id] = onde
            print(f"Insígnia {badge_id} ({nome}) não tinha ponto; fica com o ponto {onde}.")
        elif conquistada:
            sem_ponto.append(f"{badge_id} ({nome})")
        else:
            conn.execute(sa.text("DELETE FROM badges WHERE id = :b"), {"b": badge_id})
            print(f"Insígnia {badge_id} ({nome}) apagada: não tinha ponto nem conquistas.")

    if sem_ponto:
        raise RuntimeError(
            "Insígnias manuais já conquistadas e sem ponto: "
            + ", ".join(sem_ponto)
            + ". Ligue cada uma a um ponto (formulário do ponto) e rode a migração de novo."
        )

    return escolhido


def upgrade() -> None:
    conn = op.get_bind()

    escolhido = _ponto_de_cada_insignia(conn)

    with op.batch_alter_table('badges') as batch_op:
        batch_op.add_column(sa.Column('object_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('active', sa.Boolean(), server_default='1', nullable=False)
        )
        batch_op.drop_constraint('ck_badges_rule_consistency', type_='check')

    for badge_id, object_id in escolhido.items():
        conn.execute(
            sa.text("UPDATE badges SET object_id = :o WHERE id = :b"),
            {"o": object_id, "b": badge_id},
        )

    conn.execute(sa.text("UPDATE badges SET rule_type = 'point_visit' WHERE rule_type = 'manual'"))

    with op.batch_alter_table('badges') as batch_op:
        batch_op.alter_column(
            'rule_type',
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default=None,
        )
        batch_op.create_foreign_key(
            'badges_object_id_fkey', 'mupi_objects',
            ['object_id'], ['id'], ondelete='RESTRICT',
        )
        batch_op.create_index('ix_badges_object_id', ['object_id'])
        batch_op.create_check_constraint('ck_badges_rule_consistency', REGRA_NOVA)

    op.drop_index('ix_mupi_object_badges_badge_id', table_name='mupi_object_badges')
    op.drop_table('mupi_object_badges')


def downgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        'mupi_object_badges',
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('badge_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['badge_id'], ['badges.id'], name='mupi_object_badges_badge_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name='mupi_object_badges_object_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('object_id', 'badge_id', name='mupi_object_badges_pkey'),
    )
    op.create_index('ix_mupi_object_badges_badge_id', 'mupi_object_badges', ['badge_id'])

    conn.execute(sa.text(
        "INSERT INTO mupi_object_badges (object_id, badge_id) "
        "SELECT object_id, id FROM badges WHERE object_id IS NOT NULL"
    ))

    with op.batch_alter_table('badges') as batch_op:
        batch_op.drop_constraint('ck_badges_rule_consistency', type_='check')

    conn.execute(sa.text("UPDATE badges SET rule_type = 'manual' WHERE rule_type = 'point_visit'"))

    with op.batch_alter_table('badges') as batch_op:
        batch_op.drop_index('ix_badges_object_id')
        batch_op.drop_constraint('badges_object_id_fkey', type_='foreignkey')
        batch_op.drop_column('active')
        batch_op.drop_column('object_id')
        batch_op.alter_column(
            'rule_type',
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default='manual',
        )
        batch_op.create_check_constraint('ck_badges_rule_consistency', REGRA_ANTIGA)
