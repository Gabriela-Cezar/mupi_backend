"""Migração 0011: insígnia de visita com um único ponto (INS-01)."""
import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests.test_migrations import alembic_cfg


def linhas(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql)).all()]


@pytest.fixture
def banco_na_0010(tmp_path):
    url = f"sqlite:///{tmp_path / 'insignias.db'}"
    command.upgrade(alembic_cfg(url), "0010")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, password_hash) VALUES (1, 'a@b.com', 'x')"))
        conn.execute(text(
            "INSERT INTO mupi_objects (id, name, latitude, longitude) VALUES "
            "(1, 'Um', 0, 0), (2, 'Dois', 0, 0), (3, 'Três', 0, 0)"
        ))
        conn.execute(text(
            "INSERT INTO badges (id, name, rule_type, required_count) VALUES "
            "(10, 'Um ponto', 'manual', NULL), "
            "(11, 'Vários pontos', 'manual', NULL), "
            "(12, 'Sem ponto e sem dono', 'manual', NULL), "
            "(13, 'Sem ponto mas conquistada', 'manual', NULL), "
            "(14, 'Cinco pontos', 'visit_count', 5)"
        ))
        conn.execute(text(
            "INSERT INTO mupi_object_badges (object_id, badge_id) VALUES "
            "(2, 10), (3, 11), (1, 11)"
        ))
        conn.execute(text(
            "INSERT INTO user_badges (user_id, badge_id, collected_at_object_id) VALUES "
            "(1, 13, 3)"
        ))

    yield url, engine
    engine.dispose()


def test_0011_converte_as_insignias_manuais(banco_na_0010, capsys):
    url, engine = banco_na_0010

    command.upgrade(alembic_cfg(url), "0011")

    assert linhas(engine, "SELECT id, rule_type, object_id, active FROM badges ORDER BY id") == [
        (10, "point_visit", 2, 1),     # ligada a um ponto: fica com ele
        (11, "point_visit", 1, 1),     # vários: o de menor id
        (13, "point_visit", 3, 1),     # sem ponto, conquistada: onde foi ganha
        (14, "visit_count", None, 1),  # contagem não muda
    ]
    saida = capsys.readouterr().out
    assert "Insígnia 11 (Vários pontos) estava em 2 pontos" in saida
    assert "Insígnia 12 (Sem ponto e sem dono) apagada" in saida
    # A conquista continua
    assert linhas(engine, "SELECT user_id, badge_id FROM user_badges") == [(1, 13)]


def test_0011_remove_a_tabela_de_ligacao(banco_na_0010):
    url, engine = banco_na_0010

    command.upgrade(alembic_cfg(url), "0011")

    tabelas = {r[0] for r in linhas(engine, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "mupi_object_badges" not in tabelas


def test_0011_para_se_a_insignia_conquistada_nao_tem_ponto(banco_na_0010):
    url, engine = banco_na_0010
    with engine.begin() as conn:
        conn.execute(text("UPDATE user_badges SET collected_at_object_id = NULL"))

    with pytest.raises(RuntimeError, match="13 \\(Sem ponto mas conquistada\\)"):
        command.upgrade(alembic_cfg(url), "0011")


def test_desfazer_a_0011_devolve_as_ligacoes(banco_na_0010):
    url, engine = banco_na_0010
    cfg = alembic_cfg(url)
    command.upgrade(cfg, "0011")

    command.downgrade(cfg, "0010")

    assert linhas(engine, "SELECT object_id, badge_id FROM mupi_object_badges ORDER BY badge_id") == [
        (2, 10), (1, 11), (3, 13),
    ]
    assert linhas(engine, "SELECT id, rule_type FROM badges WHERE id IN (10, 14) ORDER BY id") == [
        (10, "manual"), (14, "visit_count"),
    ]
