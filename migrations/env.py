"""Configuração das migrações do banco (Alembic) — FAL-14.

O endereço do banco vem do .env (DATABASE_URL), nunca do alembic.ini, para a
senha não ir para o repositório. Os testes passam outro endereço em
`sqlalchemy.url`.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.database.all_models import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")

    if url:
        return url

    from app.core.config import DATABASE_URL

    return DATABASE_URL


def _configure_kwargs() -> dict:
    return {
        "target_metadata": target_metadata,
        # Detecta mudanças de tipo de coluna ao gerar migrações
        "compare_type": True,
        # SQLite não altera colunas/restrições direto: recria a tabela
        "render_as_batch": True,
    }


def run_migrations_offline() -> None:
    """Gera o SQL sem executar (alembic upgrade head --sql)."""
    context.configure(
        url=_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_kwargs(),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, **_configure_kwargs())

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
