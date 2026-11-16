"""Rotas no app (ROT-04): listar e ver, sempre com login.

- GET /routes — rotas ativas, com o resumo e se o usuário já concluiu;
- GET /routes/{id} — resumo + descrição, pontos em ordem e trajeto completo.

O conteúdo de cada ponto continua liberado só pela abertura com
proximidade (VIS-01); aqui vai só o resumo (nome, posição, foto).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.controller.serializers import serialize_theme
from app.core.dependencies import get_current_user
from app.database.database import get_db
from app.model.route import Route, RoutePoint
from app.model.user import User
from app.model.user_route_completion import UserRouteCompletion
from app.model.user_visit import UserVisit
from app.service import storage_service

router = APIRouter(
    prefix="/routes",
    tags=["Rotas"],
    dependencies=[Depends(get_current_user)],
)


def _options():
    return (
        selectinload(Route.points).selectinload(RoutePoint.mupi_object),
        selectinload(Route.themes),
    )


def _completed_ids(db: Session, user_id: int) -> set[int]:
    return {
        route_id for (route_id,) in
        db.query(UserRouteCompletion.route_id)
        .filter(UserRouteCompletion.user_id == user_id)
        .distinct()
    }


def serialize_route_summary(route: Route, completed: bool) -> dict:
    return {
        "id": route.id,
        "name": route.name,
        "cover_url": storage_service.url(route.cover_key),
        "distance_m": round(route.distance_m) if route.distance_m is not None else None,
        "minutes": route.minutes,
        "difficulty": route.difficulty.value,
        "age_rating": route.age_rating.value,
        "themes": [serialize_theme(t) for t in route.themes],
        "points_count": len(route.points),
        "completed": completed,
    }


def serialize_route_detail(route: Route, completed: bool, visited: set[int]) -> dict:
    return {
        **serialize_route_summary(route, completed),
        "description": route.description,
        "points": [
            {
                "id": rp.mupi_object.id,
                "name": rp.mupi_object.name,
                "latitude": rp.mupi_object.latitude,
                "longitude": rp.mupi_object.longitude,
                "photo_url": storage_service.url(rp.mupi_object.photo_key),
                "visited": rp.mupi_object.id in visited,
            }
            for rp in route.points
        ],
        # Coordenadas [longitude, latitude], do primeiro ao último ponto
        "path": route.path,
        # Posição de cada ponto em `path`: o trecho do ponto i ao i+1 é
        # path[waypoints[i]:waypoints[i+1] + 1]
        "waypoints": route.waypoints,
    }


@router.get("")
def list_routes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    routes = (
        db.query(Route)
        .options(*_options())
        .filter(Route.active.is_(True))
        .order_by(Route.name)
        .all()
    )

    completed = _completed_ids(db, user.id)

    return [serialize_route_summary(route, route.id in completed) for route in routes]


@router.get("/{route_id}")
def get_route(route_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    route = (
        db.query(Route)
        .options(*_options())
        .filter(Route.id == route_id, Route.active.is_(True))
        .first()
    )

    if route is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")

    visited = {
        object_id for (object_id,) in
        db.query(UserVisit.object_id).filter(UserVisit.user_id == user.id)
    }

    return serialize_route_detail(route, route.id in _completed_ids(db, user.id), visited)
