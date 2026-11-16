"""Migração 0008: novo modelo do ponto, com os dados já existentes."""
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from tests.test_migrations import alembic_cfg

ID = "dQw4w9WgXcQ"


@pytest.fixture
def banco_na_0007(tmp_path):
    url = f"sqlite:///{tmp_path / 'ponto.db'}"
    command.upgrade(alembic_cfg(url), "0007")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO themes (id, name) VALUES (1, 'Arte Deco'), (2, 'Modernismo')"
        ))
        conn.execute(text(
            "INSERT INTO mupi_objects (id, name, latitude, longitude, description, theme_id) VALUES "
            "(1, 'Com tudo', 0, 0, '  Texto antigo\nsegunda linha  ', 2), "
            "(2, 'Sem nada', 0, 0, NULL, NULL), "
            "(3, 'Descrição em branco', 0, 0, '   ', NULL)"
        ))
        conn.execute(text(
            "INSERT INTO mupi_object_media (id, object_id, type, url, title) VALUES "
            f"(10, 1, 'video', 'https://youtu.be/{ID}', 'Visita'), "
            "(11, 1, 'video', 'https://vimeo.com/123', NULL), "
            f"(12, 1, 'video', 'https://www.youtube.com/shorts/{ID}', NULL)"
        ))

    yield url, engine
    engine.dispose()


def linhas(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql)).all()]


def colunas(engine, tabela):
    return {c["name"] for c in inspect(engine).get_columns(tabela)}


def test_0008_converte_os_dados_existentes(banco_na_0007, capsys):
    url, engine = banco_na_0007

    command.upgrade(alembic_cfg(url), "0008")

    assert linhas(engine, "SELECT object_id, theme_id FROM mupi_object_themes") == [(1, 2)]
    assert linhas(engine, "SELECT object_id, position, title, body FROM mupi_object_sections") == [
        (1, 0, "Sobre o ponto", "Texto antigo\nsegunda linha"),
    ]
    # O link do Vimeo é descartado e avisado; os do YouTube viram ID, em ordem
    assert linhas(
        engine, "SELECT object_id, position, youtube_id, title FROM mupi_object_videos ORDER BY position"
    ) == [(1, 0, ID, "Visita"), (1, 1, ID, None)]
    assert "vimeo.com/123" in capsys.readouterr().out
    # Todos os pontos existentes continuam no mapa
    assert linhas(engine, "SELECT id, standalone FROM mupi_objects ORDER BY id") == [
        (1, 1), (2, 1), (3, 1),
    ]


def test_0008_remove_colunas_e_tabela_antigas(banco_na_0007):
    url, engine = banco_na_0007

    command.upgrade(alembic_cfg(url), "0008")

    assert "mupi_object_media" not in inspect(engine).get_table_names()
    assert {"theme_id", "description"}.isdisjoint(colunas(engine, "mupi_objects"))
    assert {"standalone", "address", "opening_hours", "accessibility"} <= colunas(engine, "mupi_objects")


def test_desfazer_a_0008_devolve_os_dados(banco_na_0007):
    url, engine = banco_na_0007
    cfg = alembic_cfg(url)
    command.upgrade(cfg, "0008")

    command.downgrade(cfg, "0007")

    assert linhas(engine, "SELECT id, theme_id, description FROM mupi_objects ORDER BY id") == [
        (1, 2, "Texto antigo\nsegunda linha"), (2, None, None), (3, None, None),
    ]
    assert linhas(engine, "SELECT object_id, type, url, title FROM mupi_object_media ORDER BY id") == [
        (1, "video", f"https://www.youtube.com/watch?v={ID}", "Visita"),
        (1, "video", f"https://www.youtube.com/watch?v={ID}", None),
    ]
