"""Regras de rota que dependem de outras telas do painel."""
from sqlalchemy.orm import Session

from app.model.route import Route, RoutePoint
from app.model.user_active_route import CancelReason
from app.service.active_route_service import cancel_progress


def routes_with_point(db: Session, point_id: int) -> list[Route]:
    return (
        db.query(Route)
        .join(RoutePoint, RoutePoint.route_id == Route.id)
        .filter(RoutePoint.object_id == point_id)
        .order_by(Route.name)
        .all()
    )


def deactivate_routes_with_point(db: Session, point_id: int) -> list[str]:
    """Ponto desativado: as rotas ativas que passam por ele são desativadas
    até serem corrigidas, senão ninguém conseguiria concluí-las (ROT-02,
    ADM-08). Devolve os nomes das rotas desativadas. Não faz commit."""
    names = []

    for route in routes_with_point(db, point_id):
        if route.active:
            route.active = False
            names.append(route.name)
            # Quem está fazendo a rota é avisado no app (ROT-10)
            cancel_progress(db, route.id, CancelReason.ROUTE_DEACTIVATED)

    return names
