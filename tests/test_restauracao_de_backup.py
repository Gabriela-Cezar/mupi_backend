"""Conferência de um backup restaurado (INF-06): app/scripts/check_restore."""
import shutil

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from app.scripts import check_restore
from tests.test_migrations import alembic_cfg


@pytest.fixture
def origem(tmp_path):
    """Banco com todas as migrações e alguns dados."""
    caminho = tmp_path / "origem.db"
    url = f"sqlite:///{caminho}"
    command.upgrade(alembic_cfg(url), "head")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO themes (id, name) VALUES (1, 'Arte Deco'), (2, 'Modernismo')"))
        conn.execute(text("INSERT INTO mupi_objects (id, name, latitude, longitude, active, standalone) VALUES (1, 'Teatro', -16.6, -49.2, 1, 1)"))
    engine.dispose()
    return caminho


def restaurar(origem, tmp_path):
    """O "backup restaurado": uma cópia do banco."""
    copia = tmp_path / "restaurado.db"
    shutil.copy(origem, copia)
    return copia


def foto(caminho):
    engine = create_engine(f"sqlite:///{caminho}")
    try:
        return check_restore.snapshot(engine)
    finally:
        engine.dispose()


def test_copia_completa_esta_ok(origem, tmp_path):
    copia = restaurar(origem, tmp_path)

    resultado = check_restore.compare(foto(origem), foto(copia))

    assert resultado.ok
    assert resultado.differences == []
    assert foto(copia).counts["themes"] == 2


def test_dados_novos_na_origem_sao_so_diferencas(origem, tmp_path):
    copia = restaurar(origem, tmp_path)
    engine = create_engine(f"sqlite:///{origem}")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO themes (id, name) VALUES (3, 'Novo')"))
    engine.dispose()

    resultado = check_restore.compare(foto(origem), foto(copia))

    assert resultado.ok
    assert resultado.differences == ["themes: origem 3, restaurado 2"]


def test_tabela_faltando_e_problema(origem, tmp_path):
    copia = restaurar(origem, tmp_path)
    engine = create_engine(f"sqlite:///{copia}")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE route_point_videos"))
    engine.dispose()

    resultado = check_restore.compare(foto(origem), foto(copia))

    assert not resultado.ok
    assert resultado.problems == ["Tabelas que faltam no restaurado: route_point_videos."]


def test_versao_diferente_e_problema(origem, tmp_path):
    copia = restaurar(origem, tmp_path)
    engine = create_engine(f"sqlite:///{copia}")
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '0016'"))
    engine.dispose()

    resultado = check_restore.compare(foto(origem), foto(copia))

    assert "Versão das migrações: origem 0017, restaurado 0016." in resultado.problems


def test_banco_vazio_e_problema(origem, tmp_path):
    vazio = tmp_path / "vazio.db"
    command.upgrade(alembic_cfg(f"sqlite:///{vazio}"), "head")

    resultado = check_restore.compare(foto(origem), foto(vazio))

    assert "O banco restaurado não tem nenhuma linha." in resultado.problems


def test_linha_de_comando(origem, tmp_path, capsys):
    copia = restaurar(origem, tmp_path)

    codigo = check_restore.main(["--source", f"sqlite:///{origem}", "--restored", f"sqlite:///{copia}"])

    assert codigo == 0
    assert "Tudo certo" in capsys.readouterr().out


def test_recusa_comparar_o_banco_com_ele_mesmo(origem, capsys):
    url = f"sqlite:///{origem}"

    assert check_restore.main(["--source", url, "--restored", url]) == 2
    assert "é o mesmo da origem" in capsys.readouterr().out


def test_nao_mostra_a_senha():
    assert check_restore._label("postgresql://u:segredo@h:5432/db") == "postgresql://u:***@h:5432/db"
