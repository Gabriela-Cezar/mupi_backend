"""Migrações do banco com Alembic (FAL-14).

Rodam o Alembic de verdade num banco SQLite temporário.
"""
import configparser
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.database.all_models import Base
from app.scripts.create_admin import admins_table_exists

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def banco(tmp_path):
    """Endereço de um banco SQLite vazio, num arquivo temporário."""
    return f"sqlite:///{tmp_path / 'migracoes.db'}"


def alembic_cfg(url: str) -> Config:
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False  # não mexe nos logs do pytest
    return cfg


def versao_atual(url: str) -> str | None:
    with create_engine(url).connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def diferencas(url: str) -> list:
    with create_engine(url).connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        return compare_metadata(ctx, Base.metadata)


def tabelas(url: str) -> set[str]:
    return set(inspect(create_engine(url)).get_table_names())


# ---------- As migrações criam o banco igual aos models ----------

def test_banco_vazio_vai_ate_a_ultima_versao(banco):
    command.upgrade(alembic_cfg(banco), "head")

    head = ScriptDirectory.from_config(alembic_cfg(banco)).get_current_head()
    assert versao_atual(banco) == head


def test_migracoes_criam_exatamente_o_banco_dos_models(banco):
    """Se alguém mudar um model e esquecer a migração, este teste falha."""
    command.upgrade(alembic_cfg(banco), "head")

    assert diferencas(banco) == []


def test_cria_todas_as_tabelas_dos_models(banco):
    command.upgrade(alembic_cfg(banco), "head")

    assert tabelas(banco) == set(Base.metadata.tables) | {"alembic_version"}


def test_desfazer_tudo_remove_as_tabelas(banco):
    cfg = alembic_cfg(banco)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "base")

    assert tabelas(banco) == {"alembic_version"}
    assert versao_atual(banco) is None


def test_desfazer_e_refazer_funciona(banco):
    cfg = alembic_cfg(banco)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    command.upgrade(cfg, "head")

    assert diferencas(banco) == []


def test_cada_migracao_pode_ser_desfeita_e_refeita_uma_a_uma(banco):
    cfg = alembic_cfg(banco)
    revisoes = [
        r.revision for r in reversed(list(ScriptDirectory.from_config(cfg).walk_revisions()))
    ]

    for revisao in revisoes:
        command.upgrade(cfg, revisao)
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, revisao)

    assert versao_atual(banco) == revisoes[-1]


# ---------- Histórico das migrações ----------

def test_historico_e_uma_linha_so(banco):
    """Duas migrações com o mesmo "pai" (ex.: em branches diferentes) criam
    duas pontas; o Alembic não saberia qual aplicar."""
    script = ScriptDirectory.from_config(alembic_cfg(banco))

    assert len(script.get_heads()) == 1


def test_primeiras_migracoes(banco):
    script = ScriptDirectory.from_config(alembic_cfg(banco))

    assert script.get_revision("0001").down_revision is None
    assert script.get_revision("0002").down_revision == "0001"


def test_0002_nao_faz_nada_fora_do_postgresql(banco):
    cfg = alembic_cfg(banco)
    command.upgrade(cfg, "0001")
    antes = tabelas(banco)

    command.upgrade(cfg, "0002")

    assert tabelas(banco) == antes
    assert diferencas(banco) == []


# ---------- Nomes das restrições iguais aos do PostgreSQL ----------

@pytest.mark.parametrize("tabela, tipo, nome", [
    ("badges", "fk", "badges_theme_id_fkey"),
    ("user_visits", "fk", "user_visits_object_id_fkey"),
    ("user_badges", "fk", "user_badges_badge_id_fkey"),
    ("users", "pk", "users_pkey"),
    ("badges", "uq", "badges_name_key"),
    ("themes", "uq", "themes_name_key"),
])
def test_nomes_das_restricoes_seguem_o_padrao_do_postgresql(tabela, tipo, nome):
    """As migrações futuras (ex.: FAL-11) precisam saber esses nomes."""
    from sqlalchemy import ForeignKeyConstraint, PrimaryKeyConstraint, UniqueConstraint

    classe = {"fk": ForeignKeyConstraint, "pk": PrimaryKeyConstraint, "uq": UniqueConstraint}[tipo]
    nomes = {
        c.name for c in Base.metadata.tables[tabela].constraints if isinstance(c, classe)
    }

    assert nome in nomes


# ---------- Configuração ----------

def test_todos_os_models_estao_registrados_para_as_migracoes():
    """Um model novo esquecido em all_models.py não teria migração gerada."""
    registrados = (RAIZ / "app/database/all_models.py").read_text(encoding="utf-8")

    for arquivo in sorted((RAIZ / "app/model").glob("*.py")):
        if arquivo.name == "__init__.py":
            continue
        assert f"from app.model.{arquivo.stem} import" in registrados, arquivo.name


def test_alembic_ini_nao_guarda_o_endereco_do_banco():
    """A senha do banco não pode ir para o repositório."""
    ini = configparser.ConfigParser()
    ini.read(RAIZ / "alembic.ini", encoding="utf-8")

    assert ini.get("alembic", "sqlalchemy.url", fallback="").strip() == ""


def test_scripts_que_apagavam_tabelas_foram_removidos():
    assert not (RAIZ / "create_tables.py").exists()
    assert not (RAIZ / "reset_mupi_tables.py").exists()


# ---------- create_admin ----------

def test_create_admin_detecta_banco_sem_migracoes(banco):
    assert admins_table_exists(create_engine(banco)) is False


def test_create_admin_detecta_banco_com_migracoes(banco):
    command.upgrade(alembic_cfg(banco), "head")

    assert admins_table_exists(create_engine(banco)) is True


def test_create_admin_nao_cria_tabela_e_explica_o_que_fazer(banco, monkeypatch, capsys):
    from app.scripts import create_admin

    vazio = create_engine(banco)
    monkeypatch.setattr(create_admin, "engine", vazio)
    monkeypatch.setattr(create_admin, "admins_table_exists", lambda: admins_table_exists(vazio))

    with pytest.raises(SystemExit) as saida:
        create_admin.main()

    assert saida.value.code == 1
    assert "alembic upgrade head" in capsys.readouterr().out
    assert tabelas(banco) == set()
