"""Confere se um backup restaurado está completo (INF-06).

Uso (na raiz do projeto):
    python -m app.scripts.check_restore --restored postgresql://usuario:senha@host:5432/mupi_restaurado

Compara o banco restaurado com o banco do .env (DATABASE_URL), ou com outro
(--source URL): versão das migrações, tabelas e quantidade de linhas de
cada uma. Só lê os dois bancos; nada é alterado.

Diferenças de linhas são esperadas se o banco de origem mudou depois do
backup (ex.: visitas novas em produção); a versão das migrações e as
tabelas devem ser iguais. O passo a passo está em infra/backup_e_restauracao.md.
"""
import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url

from app.core import config


@dataclass
class DatabaseSnapshot:
    migration: str | None
    counts: dict[str, int]


def snapshot(engine: Engine) -> DatabaseSnapshot:
    """Versão das migrações e linhas de cada tabela."""
    tables = sorted(inspect(engine).get_table_names())

    with engine.connect() as conn:
        migration = None
        if "alembic_version" in tables:
            migration = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

        counts = {
            table: conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
            for table in tables
        }

    return DatabaseSnapshot(migration=migration, counts=counts)


@dataclass
class Comparison:
    problems: list[str] = field(default_factory=list)
    differences: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def compare(source: DatabaseSnapshot, restored: DatabaseSnapshot) -> Comparison:
    """Problemas (o backup está incompleto) e diferenças de linhas (podem ser
    só dados novos na origem depois do backup)."""
    result = Comparison()

    if restored.migration != source.migration:
        result.problems.append(
            f"Versão das migrações: origem {source.migration}, restaurado {restored.migration}."
        )

    missing = sorted(set(source.counts) - set(restored.counts))
    extra = sorted(set(restored.counts) - set(source.counts))

    if missing:
        result.problems.append(f"Tabelas que faltam no restaurado: {', '.join(missing)}.")
    if extra:
        result.problems.append(f"Tabelas a mais no restaurado: {', '.join(extra)}.")

    # Só os dados: a alembic_version sempre tem uma linha
    data = {t: n for t, n in restored.counts.items() if t != "alembic_version"}
    if any(n for t, n in source.counts.items() if t != "alembic_version") and not any(data.values()):
        result.problems.append("O banco restaurado não tem nenhuma linha.")

    for table in sorted(set(source.counts) & set(restored.counts)):
        if source.counts[table] != restored.counts[table]:
            result.differences.append(
                f"{table}: origem {source.counts[table]}, restaurado {restored.counts[table]}"
            )

    return result


def _label(url: str) -> str:
    """O endereço do banco sem a senha, para mostrar na tela."""
    return make_url(url).render_as_string(hide_password=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Confere um backup restaurado (INF-06).")
    parser.add_argument("--restored", required=True, help="URL do banco restaurado")
    parser.add_argument("--source", default=None, help="URL do banco de origem (padrão: DATABASE_URL)")
    args = parser.parse_args(argv)

    source_url = args.source or config.DATABASE_URL

    if make_url(source_url) == make_url(args.restored):
        print("Erro: o banco restaurado é o mesmo da origem.")
        return 2

    source = snapshot(create_engine(source_url))
    restored = snapshot(create_engine(args.restored))
    result = compare(source, restored)

    print(f"Origem:      {_label(source_url)} (migração {source.migration}, {len(source.counts)} tabelas)")
    print(f"Restaurado:  {_label(args.restored)} (migração {restored.migration}, {len(restored.counts)} tabelas)\n")

    for table, count in restored.counts.items():
        print(f"  {table}: {count}")

    if result.differences:
        print("\nLinhas diferentes (normal se a origem mudou depois do backup):")
        for line in result.differences:
            print(f"  {line}")

    if not result.ok:
        print("\nProblemas encontrados:")
        for problem in result.problems:
            print(f"✗ {problem}")
        return 1

    print("\nTudo certo: o backup foi restaurado com todas as tabelas e a mesma versão.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
