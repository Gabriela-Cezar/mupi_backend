"""Trajeto a pé da rota pelo OpenRouteService (ROT-03)."""
import pytest

from app.core import config
from app.model.mupi_object import MupiObject
from app.model.route import AgeRating, Route, RouteDifficulty, RoutePoint
from app.service.route_path_service import (
    MAX_ROUTE_POINTS,
    RoutePathError,
    compute_route_path,
    update_route_path,
)
from tests.ors_falso import RespostaFalsa

A, B, C = (-16.68, -49.25), (-16.69, -49.26), (-16.70, -49.27)


def test_pede_o_trajeto_a_pe_passando_pelos_pontos_na_ordem(ors):
    resultado = compute_route_path([A, B, C])

    pedido = ors.pedidos[-1]
    assert pedido["url"].endswith("/foot-walking")
    assert pedido["headers"]["Authorization"] == "chave-de-teste"
    # O serviço usa [longitude, latitude]
    assert ors.coordenadas_pedidas == [[-49.25, -16.68], [-49.26, -16.69], [-49.27, -16.70]]
    assert resultado.distance_m == 1234.5
    assert resultado.walk_seconds == 900


def test_devolve_o_caminho_e_a_posicao_de_cada_ponto(ors):
    resultado = compute_route_path([A, B, C])

    # Um ponto intermediário entre cada par: A, meio, B, meio, C
    assert len(resultado.path) == 5
    assert resultado.waypoints == [0, 2, 4]
    assert resultado.path[2] == pytest.approx([-49.26, -16.69])


@pytest.mark.parametrize("pontos, mensagem", [
    ([A], "pelo menos 2 pontos"),
    ([A] * (MAX_ROUTE_POINTS + 1), f"no máximo {MAX_ROUTE_POINTS} pontos"),
])
def test_quantidade_de_pontos_invalida(ors, pontos, mensagem):
    with pytest.raises(RoutePathError, match=mensagem):
        compute_route_path(pontos)

    assert ors.pedidos == []


def test_sem_chave_configurada(ors, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTESERVICE_API_KEY", None)

    with pytest.raises(RoutePathError, match="OPENROUTESERVICE_API_KEY"):
        compute_route_path([A, B])


def test_sem_conexao(ors):
    ors.erro_de_conexao = True

    with pytest.raises(RoutePathError, match="Não foi possível conectar"):
        compute_route_path([A, B])


@pytest.mark.parametrize("status, corpo, mensagem", [
    (403, {"error": "Access denied"}, "recusou a chave"),
    (429, {"error": "Quota exceeded"}, "Cota do serviço de trajetos esgotada"),
    (404, {"error": {"code": 2010, "message": "Could not find routable point within a radius of 350.0 meters"}},
     "Could not find routable point"),
    (500, {}, "erro 500"),
])
def test_erros_do_servico_viram_mensagens_para_o_painel(ors, status, corpo, mensagem):
    ors.resposta = RespostaFalsa(status, corpo)

    with pytest.raises(RoutePathError, match=mensagem):
        compute_route_path([A, B])


@pytest.mark.parametrize("corpo", [
    {},
    {"routes": []},
    {"routes": [{"summary": {}, "geometry": "", "way_points": [0, 1]}]},
    {"routes": [{"summary": {"distance": 1}, "geometry": "_p~iF~ps|U", "way_points": [0]}]},
])
def test_resposta_inesperada(ors, corpo):
    ors.resposta = RespostaFalsa(200, corpo)

    with pytest.raises(RoutePathError, match="resposta inesperada"):
        compute_route_path([A, B])


# ---------- Guardar na rota ----------

@pytest.fixture
def rota(db_session):
    pontos = [
        MupiObject(name=f"P{i}", latitude=lat, longitude=lng)
        for i, (lat, lng) in enumerate([A, B])
    ]
    db_session.add_all(pontos)
    db_session.flush()

    route = Route(
        name="Centro", difficulty=RouteDifficulty.EASY, age_rating=AgeRating.FREE, active=True,
        points=[RoutePoint(object_id=p.id, position=i, mupi_object=p) for i, p in enumerate(pontos)],
    )
    db_session.add(route)
    db_session.commit()
    return route


def test_guarda_o_trajeto_na_rota(ors, rota):
    assert update_route_path(rota) is True

    assert rota.has_path
    assert rota.waypoints == [0, 2]
    assert rota.distance_m == 1234.5
    assert rota.walk_seconds == 900
    assert rota.path_error is None
    assert rota.path_computed_at is not None
    # Sem tempo estimado, vale o de caminhada
    assert rota.minutes == 15


def test_com_erro_a_rota_fica_sem_trajeto_e_desativada(ors, rota):
    update_route_path(rota)
    ors.resposta = RespostaFalsa(429, {})

    assert update_route_path(rota) is False

    assert not rota.has_path
    assert rota.path is None
    assert rota.distance_m is None
    assert "Cota" in rota.path_error
    assert rota.active is False


def test_tempo_estimado_editado_vale_mais_que_a_caminhada(ors, rota):
    update_route_path(rota)
    rota.estimated_minutes = 45

    assert rota.minutes == 45
