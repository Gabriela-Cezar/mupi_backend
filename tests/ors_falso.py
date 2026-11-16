"""OpenRouteService simulado para os testes de rota (nada sai para a rede)."""
import polyline
import pytest

from app.core import config
from app.service import route_path_service


class RespostaFalsa:
    def __init__(self, status_code: int, corpo: dict):
        self.status_code = status_code
        self._corpo = corpo
        self.text = str(corpo)

    def json(self):
        return self._corpo


def resposta_de_trajeto(coordenadas: list[list[float]], distancia=1234.5, duracao=900.0):
    """Resposta como a do OpenRouteService: um caminho reto que passa por
    cada ponto ([longitude, latitude]), com um ponto intermediário entre eles."""
    caminho = []
    waypoints = []

    for i, (lng, lat) in enumerate(coordenadas):
        if i > 0:
            ant_lng, ant_lat = coordenadas[i - 1]
            caminho.append(((ant_lat + lat) / 2, (ant_lng + lng) / 2))
        waypoints.append(len(caminho))
        caminho.append((lat, lng))

    return RespostaFalsa(200, {
        "routes": [{
            "summary": {"distance": distancia, "duration": duracao},
            "geometry": polyline.encode(caminho),
            "way_points": waypoints,
        }]
    })


class OrsFalso:
    """Grava os pedidos e responde com um trajeto (ou com a resposta definida)."""

    def __init__(self):
        self.pedidos: list[dict] = []
        self.resposta = None  # None = trajeto que passa pelos pontos pedidos
        self.erro_de_conexao = False

    def post(self, url, headers=None, json=None, timeout=None):
        self.pedidos.append({"url": url, "headers": headers, "json": json})

        if self.erro_de_conexao:
            raise route_path_service.requests.ConnectionError("fora do ar")

        if self.resposta is not None:
            return self.resposta

        return resposta_de_trajeto(json["coordinates"])

    @property
    def coordenadas_pedidas(self) -> list[list[float]]:
        return self.pedidos[-1]["json"]["coordinates"]


@pytest.fixture
def ors(monkeypatch):
    falso = OrsFalso()
    monkeypatch.setattr(config, "OPENROUTESERVICE_API_KEY", "chave-de-teste")
    monkeypatch.setattr(route_path_service.requests, "post", falso.post)
    return falso
