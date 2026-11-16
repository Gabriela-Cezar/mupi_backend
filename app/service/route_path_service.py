"""Trajeto a pé da rota, pelo OpenRouteService (ROT-03).

Calculado ao salvar a rota (ou mudar os pontos/a ordem) e guardado no banco:
coordenadas, distância, tempo de caminhada e a posição de cada ponto no
trajeto (para o app destacar o trecho atual). Todos os usuários reutilizam o
mesmo trajeto: economiza a cota do serviço e deixa o app rápido.

Se o cálculo falhar, a rota fica sem trajeto, com o erro guardado, e não pode
ser ativada até o "recalcular trajeto" dar certo.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import polyline
import requests

from app.core import config
from app.model.route import Route

logger = logging.getLogger(__name__)

ORS_URL = "https://api.heigit.org/openrouteservice/v2/directions/foot-walking"

# Limite de pontos por pedido no plano gratuito do OpenRouteService
MAX_ROUTE_POINTS = 50


class RoutePathError(Exception):
    """O trajeto não pôde ser calculado; a mensagem vai para o painel."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class RoutePath:
    path: list[list[float]]
    waypoints: list[int]
    distance_m: float
    walk_seconds: int


def compute_route_path(points: list[tuple[float, float]]) -> RoutePath:
    """Trajeto a pé passando por [points] ((latitude, longitude)), na ordem."""
    if len(points) < 2:
        raise RoutePathError("A rota precisa de pelo menos 2 pontos.")

    if len(points) > MAX_ROUTE_POINTS:
        raise RoutePathError(f"A rota pode ter no máximo {MAX_ROUTE_POINTS} pontos.")

    api_key = config.OPENROUTESERVICE_API_KEY

    if not api_key:
        raise RoutePathError(
            "Chave do OpenRouteService não configurada (OPENROUTESERVICE_API_KEY)."
        )

    body = {
        "coordinates": [[lng, lat] for lat, lng in points],
        "geometry": True,
        "instructions": False,
    }

    try:
        response = requests.post(
            ORS_URL,
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            json=body,
            timeout=30,
        )
    except requests.RequestException:
        logger.exception("Erro de conexão com o OpenRouteService")
        raise RoutePathError("Não foi possível conectar ao serviço de trajetos.")

    if response.status_code != 200:
        logger.warning(
            "OpenRouteService respondeu %s: %s", response.status_code, response.text[:500]
        )
        raise RoutePathError(_provider_message(response))

    try:
        route = response.json()["routes"][0]
        coordinates = polyline.decode(route["geometry"])
        waypoints = [int(i) for i in route["way_points"]]
        summary = route["summary"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise RoutePathError("O serviço de trajetos devolveu uma resposta inesperada.")

    if len(waypoints) != len(points) or not coordinates:
        raise RoutePathError("O serviço de trajetos devolveu uma resposta inesperada.")

    return RoutePath(
        path=[[lng, lat] for lat, lng in coordinates],
        waypoints=waypoints,
        distance_m=float(summary.get("distance", 0)),
        walk_seconds=round(summary.get("duration", 0)),
    )


def _provider_message(response) -> str:
    """Erro do serviço, em português, com o detalhe útil para o painel."""
    detail = ""

    try:
        error = response.json().get("error")
        detail = error.get("message", "") if isinstance(error, dict) else str(error or "")
    except ValueError:
        pass

    if response.status_code in (401, 403):
        return "O serviço de trajetos recusou a chave (OPENROUTESERVICE_API_KEY)."

    if response.status_code == 429:
        return "Cota do serviço de trajetos esgotada. Tente de novo mais tarde."

    base = f"Não foi possível calcular o trajeto (erro {response.status_code})."

    # Ex.: um ponto longe de qualquer rua
    return f"{base} {detail}".strip() if detail else base


def update_route_path(route: Route) -> bool:
    """Recalcula e guarda o trajeto da rota. Não faz commit.

    Devolve True se deu certo. Com erro, a rota fica sem trajeto, com a
    mensagem em `path_error`, e é desativada (não pode ficar ativa sem
    trajeto).
    """
    points = [(rp.mupi_object.latitude, rp.mupi_object.longitude) for rp in route.points]

    try:
        result = compute_route_path(points)
    except RoutePathError as exc:
        route.path = None
        route.waypoints = None
        route.distance_m = None
        route.walk_seconds = None
        route.path_error = exc.message
        route.path_computed_at = None
        route.active = False
        return False

    route.path = result.path
    route.waypoints = result.waypoints
    route.distance_m = result.distance_m
    route.walk_seconds = result.walk_seconds
    route.path_error = None
    route.path_computed_at = datetime.now(timezone.utc)
    return True
