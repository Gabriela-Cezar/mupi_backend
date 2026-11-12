"""Busca por nome trata "%" e "_" como texto, não como curinga (FAL-17)."""
import pytest

from app.model.mupi_object import MupiObject

LAT, LNG = -16.6857, -49.2462

NOMES = [
    "Teatro 100% Goiano",
    "Teatro Goiânia",
    "Casa_Azul",
    "CasaXAzul",
    "Galeria a/b",
    "Galeria ab",
    "Estúdio C:\\Arte",
    "Estúdio C:Arte",
]


@pytest.fixture
def pontos(db_session):
    for nome in NOMES:
        db_session.add(MupiObject(name=nome, latitude=LAT, longitude=LNG))
    db_session.commit()


def busca_app(user_client, termo):
    resposta = user_client.get(
        "/mupi-objects/search",
        params={"name": termo, "latitude": LAT, "longitude": LNG},
    )
    assert resposta.status_code == 200
    return sorted(item["name"] for item in resposta.json())


def busca_painel(admin_client, termo):
    resposta = admin_client.get("/admin/search", params={"name": termo})
    assert resposta.status_code == 200
    return sorted(item["name"] for item in resposta.json())


CASOS = [
    # (termo digitado, nomes encontrados)
    ("%", ["Teatro 100% Goiano"]),
    ("100%", ["Teatro 100% Goiano"]),
    ("% Goi", ["Teatro 100% Goiano"]),
    ("_", ["Casa_Azul"]),
    ("Casa_Azul", ["Casa_Azul"]),
    ("a/b", ["Galeria a/b"]),          # "/" é o caractere de escape usado
    ("C:\\Arte", ["Estúdio C:\\Arte"]),  # barra invertida também é texto
    ("teatro", ["Teatro 100% Goiano", "Teatro Goiânia"]),  # continua sem diferenciar maiúsculas
    ("goi", ["Teatro 100% Goiano", "Teatro Goiânia"]),     # e encontra no meio do nome
]


@pytest.mark.parametrize("termo, esperado", CASOS)
def test_busca_do_app(user_client, pontos, termo, esperado):
    assert busca_app(user_client, termo) == esperado


@pytest.mark.parametrize("termo, esperado", CASOS)
def test_busca_do_painel(admin_client, pontos, termo, esperado):
    assert busca_painel(admin_client, termo) == esperado


def test_percentual_nao_lista_todos_os_pontos(user_client, pontos):
    """Antes, buscar "%" devolvia todos os pontos ativos."""
    assert len(busca_app(user_client, "%")) < len(NOMES)


def test_busca_do_app_continua_ignorando_pontos_desativados(user_client, db_session):
    db_session.add_all([
        MupiObject(name="Praça 50%", latitude=LAT, longitude=LNG),
        MupiObject(name="Museu 50%", latitude=LAT, longitude=LNG, active=False),
    ])
    db_session.commit()

    assert busca_app(user_client, "50%") == ["Praça 50%"]
