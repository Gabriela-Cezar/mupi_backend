"""Estado inicial do banco (FAL-14).

Cria todas as tabelas como estavam nos models quando o Alembic foi adotado.
Num banco novo (ex.: na AWS), `alembic upgrade head` cria tudo a partir daqui.
O banco de desenvolvimento, que já tinha as tabelas, foi marcado com
`alembic stamp 0001` (sem executar esta migração) e corrigido pela 0002.

Revision ID: 0001
Revises:
Create Date: 2026-11-11 18:23:56.412821
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('admins',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('admins_pkey'))
    )
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_admins_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_admins_id'), ['id'], unique=False)

    op.create_table('themes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('themes_pkey')),
    sa.UniqueConstraint('name', name=op.f('themes_name_key'))
    )
    with op.batch_alter_table('themes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_themes_id'), ['id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('email_verified', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('users_pkey'))
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_id'), ['id'], unique=False)

    op.create_table('badges',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('image', sa.LargeBinary(), nullable=True),
    sa.Column('image_mime_type', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('rule_type', sa.Enum('manual', 'visit_count', 'theme_visit_count', name='badge_rule', native_enum=False, length=30), server_default='manual', nullable=False),
    sa.Column('required_count', sa.Integer(), nullable=True),
    sa.Column('theme_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("(rule_type = 'manual' AND required_count IS NULL AND theme_id IS NULL) OR (rule_type = 'visit_count' AND required_count >= 1 AND theme_id IS NULL) OR (rule_type = 'theme_visit_count' AND required_count >= 1 AND theme_id IS NOT NULL)", name='ck_badges_rule_consistency'),
    sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], name=op.f('badges_theme_id_fkey'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('badges_pkey')),
    sa.UniqueConstraint('name', name=op.f('badges_name_key'))
    )
    with op.batch_alter_table('badges', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_badges_id'), ['id'], unique=False)

    op.create_table('mupi_objects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('theme_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('latitude BETWEEN -90 AND 90', name='ck_mupi_objects_latitude_range'),
    sa.CheckConstraint('longitude BETWEEN -180 AND 180', name='ck_mupi_objects_longitude_range'),
    sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], name=op.f('mupi_objects_theme_id_fkey'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('mupi_objects_pkey'))
    )
    with op.batch_alter_table('mupi_objects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mupi_objects_active'), ['active'], unique=False)
        batch_op.create_index(batch_op.f('ix_mupi_objects_id'), ['id'], unique=False)
        batch_op.create_index('ix_mupi_objects_lat_lng', ['latitude', 'longitude'], unique=False)
        batch_op.create_index(batch_op.f('ix_mupi_objects_theme_id'), ['theme_id'], unique=False)

    op.create_table('mupi_object_badges',
    sa.Column('object_id', sa.Integer(), nullable=False),
    sa.Column('badge_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['badge_id'], ['badges.id'], name=op.f('mupi_object_badges_badge_id_fkey'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name=op.f('mupi_object_badges_object_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('object_id', 'badge_id', name=op.f('mupi_object_badges_pkey'))
    )
    with op.batch_alter_table('mupi_object_badges', schema=None) as batch_op:
        batch_op.create_index('ix_mupi_object_badges_badge_id', ['badge_id'], unique=False)

    op.create_table('mupi_object_media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('object_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('image', 'video', name='media_type'), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=True),
    sa.Column('mime_type', sa.String(length=100), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('title', sa.String(length=150), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('(data IS NOT NULL) <> (url IS NOT NULL)', name='ck_mupi_object_media_data_xor_url'),
    sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name=op.f('mupi_object_media_object_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('mupi_object_media_pkey'))
    )
    with op.batch_alter_table('mupi_object_media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mupi_object_media_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mupi_object_media_object_id'), ['object_id'], unique=False)

    op.create_table('user_badges',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('badge_id', sa.Integer(), nullable=False),
    sa.Column('collected_at_object_id', sa.Integer(), nullable=True),
    sa.Column('collected_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['badge_id'], ['badges.id'], name=op.f('user_badges_badge_id_fkey'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['collected_at_object_id'], ['mupi_objects.id'], name=op.f('user_badges_collected_at_object_id_fkey'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('user_badges_user_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'badge_id', name=op.f('user_badges_pkey'))
    )
    with op.batch_alter_table('user_badges', schema=None) as batch_op:
        batch_op.create_index('ix_user_badges_badge_id', ['badge_id'], unique=False)

    op.create_table('user_visits',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('object_id', sa.Integer(), nullable=False),
    sa.Column('visited_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['object_id'], ['mupi_objects.id'], name=op.f('user_visits_object_id_fkey'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('user_visits_user_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'object_id', name=op.f('user_visits_pkey'))
    )
    with op.batch_alter_table('user_visits', schema=None) as batch_op:
        batch_op.create_index('ix_user_visits_object_id', ['object_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('user_visits', schema=None) as batch_op:
        batch_op.drop_index('ix_user_visits_object_id')

    op.drop_table('user_visits')
    with op.batch_alter_table('user_badges', schema=None) as batch_op:
        batch_op.drop_index('ix_user_badges_badge_id')

    op.drop_table('user_badges')
    with op.batch_alter_table('mupi_object_media', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mupi_object_media_object_id'))
        batch_op.drop_index(batch_op.f('ix_mupi_object_media_id'))

    op.drop_table('mupi_object_media')
    with op.batch_alter_table('mupi_object_badges', schema=None) as batch_op:
        batch_op.drop_index('ix_mupi_object_badges_badge_id')

    op.drop_table('mupi_object_badges')
    with op.batch_alter_table('mupi_objects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mupi_objects_theme_id'))
        batch_op.drop_index('ix_mupi_objects_lat_lng')
        batch_op.drop_index(batch_op.f('ix_mupi_objects_id'))
        batch_op.drop_index(batch_op.f('ix_mupi_objects_active'))

    op.drop_table('mupi_objects')
    with op.batch_alter_table('badges', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_badges_id'))

    op.drop_table('badges')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_id'))
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    with op.batch_alter_table('themes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_themes_id'))

    op.drop_table('themes')
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_admins_id'))
        batch_op.drop_index(batch_op.f('ix_admins_email'))

    op.drop_table('admins')

    # No PostgreSQL o ENUM é um tipo à parte e não some junto com a tabela
    sa.Enum(name='media_type').drop(op.get_bind(), checkfirst=True)
