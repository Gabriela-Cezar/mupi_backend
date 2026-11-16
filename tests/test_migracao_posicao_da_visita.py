"""Migração 0009: posição e precisão na visita (VIS-03)."""
from alembic import command
from sqlalchemy import create_engine, inspect, text

from tests.test_migrations import alembic_cfg


def colunas(engine):
    return {c["name"] for c in inspect(engine).get_columns("user_visits")}


def test_0009_mantem_as_visitas_antigas_com_posicao_nula(tmp_path):
    url = f"sqlite:///{tmp_path / 'visitas.db'}"
    cfg = alembic_cfg(url)
    command.upgrade(cfg, "0008")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, email, password_hash) VALUES (1, 'a@b.com', 'x')"
        ))
        conn.execute(text(
            "INSERT INTO mupi_objects (id, name, latitude, longitude) VALUES (1, 'P', 0, 0)"
        ))
        conn.execute(text("INSERT INTO user_visits (user_id, object_id) VALUES (1, 1)"))

    command.upgrade(cfg, "0009")

    with engine.connect() as conn:
        linha = conn.execute(text(
            "SELECT user_id, object_id, latitude, longitude, accuracy FROM user_visits"
        )).one()
    assert tuple(linha) == (1, 1, None, None, None)

    command.downgrade(cfg, "0008")

    assert {"latitude", "longitude", "accuracy"}.isdisjoint(colunas(engine))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM user_visits")).scalar() == 1
    engine.dispose()
