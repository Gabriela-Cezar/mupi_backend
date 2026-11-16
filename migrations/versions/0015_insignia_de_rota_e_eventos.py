"""Insígnia de conclusão de rota (INS-04, INS-07) e eventos de rota (ADM-10).

- badges.route_id (única: uma insígnia de conclusão por rota) e o tipo
  route_completion na regra de consistência;
- user_badges.collected_at_route_id: a rota onde a insígnia foi ganha;
- route_events: rota iniciada, abandonada, concluída ou encerrada.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cópia da regra do modelo nesta versão (a migração não pode mudar depois)
BADGE_RULE_CHECK = (
    "(rule_type = 'point_visit' AND object_id IS NOT NULL "
    "AND required_count IS NULL AND theme_id IS NULL AND route_id IS NULL) "
    "OR (rule_type = 'visit_count' AND required_count IS NOT NULL "
    "AND required_count >= 1 AND object_id IS NULL AND theme_id IS NULL "
    "AND route_id IS NULL) "
    "OR (rule_type = 'theme_visit_count' AND required_count IS NOT NULL "
    "AND required_count >= 1 AND theme_id IS NOT NULL AND object_id IS NULL "
    "AND route_id IS NULL) "
    "OR (rule_type = 'route_completion' AND route_id IS NOT NULL "
    "AND object_id IS NULL AND theme_id IS NULL AND required_count IS NULL)"
)

REGRA_DA_0011 = (
    "(rule_type = 'point_visit' AND object_id IS NOT NULL "
    "AND required_count IS NULL AND theme_id IS NULL) "
    "OR (rule_type = 'visit_count' AND required_count IS NOT NULL "
    "AND required_count >= 1 AND object_id IS NULL AND theme_id IS NULL) "
    "OR (rule_type = 'theme_visit_count' AND required_count IS NOT NULL "
    "AND required_count >= 1 AND theme_id IS NOT NULL AND object_id IS NULL)"
)


def upgrade() -> None:
    with op.batch_alter_table('badges') as batch_op:
        batch_op.add_column(sa.Column('route_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('ck_badges_rule_consistency', type_='check')

    with op.batch_alter_table('badges') as batch_op:
        batch_op.create_foreign_key(
            'badges_route_id_fkey', 'routes', ['route_id'], ['id'], ondelete='RESTRICT',
        )
        batch_op.create_unique_constraint('badges_route_id_key', ['route_id'])
        batch_op.create_check_constraint('ck_badges_rule_consistency', BADGE_RULE_CHECK)

    with op.batch_alter_table('user_badges') as batch_op:
        batch_op.add_column(sa.Column('collected_at_route_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'user_badges_collected_at_route_id_fkey', 'routes',
            ['collected_at_route_id'], ['id'], ondelete='SET NULL',
        )

    op.create_table(
        'route_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='route_events_user_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['route_id'], ['routes.id'], name='route_events_route_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='route_events_pkey'),
    )
    op.create_index('ix_route_events_route_kind', 'route_events', ['route_id', 'kind'])
    op.create_index('ix_route_events_user_id', 'route_events', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_route_events_user_id', table_name='route_events')
    op.drop_index('ix_route_events_route_kind', table_name='route_events')
    op.drop_table('route_events')

    with op.batch_alter_table('user_badges') as batch_op:
        batch_op.drop_constraint('user_badges_collected_at_route_id_fkey', type_='foreignkey')
        batch_op.drop_column('collected_at_route_id')

    # Insígnias de rota não existiam antes da 0015
    op.execute("DELETE FROM user_badges WHERE badge_id IN (SELECT id FROM badges WHERE rule_type = 'route_completion')")
    op.execute("DELETE FROM badges WHERE rule_type = 'route_completion'")

    with op.batch_alter_table('badges') as batch_op:
        batch_op.drop_constraint('ck_badges_rule_consistency', type_='check')
        batch_op.drop_constraint('badges_route_id_key', type_='unique')
        batch_op.drop_constraint('badges_route_id_fkey', type_='foreignkey')
        batch_op.drop_column('route_id')
        batch_op.create_check_constraint('ck_badges_rule_consistency', REGRA_DA_0011)
