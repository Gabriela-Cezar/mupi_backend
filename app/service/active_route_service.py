"""Rota ativa do usuário (ROT-05 a ROT-10)."""
from sqlalchemy.orm import Session, selectinload

from app.model.route import Route, RoutePoint
from app.model.route_event import RouteEvent, RouteEventKind
from app.model.user_active_route import CancelReason, UserActiveRoute

NOTICES = {
    CancelReason.ROUTE_UPDATED: "Esta rota foi atualizada; inicie novamente.",
    CancelReason.ROUTE_DEACTIVATED: "Esta rota não está mais disponível; o seu progresso foi encerrado.",
}

# Estado de cada ponto da rota ativa (ROT-06)
DONE = "done"
CURRENT = "current"
PENDING = "pending"


def get_progress(db: Session, user_id: int) -> UserActiveRoute | None:
    return (
        db.query(UserActiveRoute)
        .options(
            selectinload(UserActiveRoute.route)
            .selectinload(Route.points)
            .selectinload(RoutePoint.mupi_object),
            selectinload(UserActiveRoute.route).selectinload(Route.themes),
        )
        .filter(UserActiveRoute.user_id == user_id)
        .first()
    )


def active_route_point_ids(db: Session, user_id: int) -> set[int]:
    """Pontos da rota que o usuário está fazendo (vazio se nenhuma)."""
    rows = (
        db.query(RoutePoint.object_id)
        .join(UserActiveRoute, UserActiveRoute.route_id == RoutePoint.route_id)
        .filter(
            UserActiveRoute.user_id == user_id,
            UserActiveRoute.cancelled_reason.is_(None),
        )
    )
    return {object_id for (object_id,) in rows}


def record_event(db: Session, user_id: int, route_id: int, kind: str) -> None:
    """Rota iniciada, abandonada, concluída ou encerrada (ADM-10)."""
    db.add(RouteEvent(user_id=user_id, route_id=route_id, kind=kind))


def cancel_progress(db: Session, route_id: int, reason: str) -> int:
    """Encerra o progresso de quem está fazendo a rota (ROT-10). O app
    mostra o aviso na próxima consulta. Devolve quantos usuários. Não faz
    commit."""
    query = db.query(UserActiveRoute).filter(
        UserActiveRoute.route_id == route_id,
        UserActiveRoute.cancelled_reason.is_(None),
    )

    user_ids = [user_id for (user_id,) in query.with_entities(UserActiveRoute.user_id)]

    for user_id in user_ids:
        record_event(db, user_id, route_id, RouteEventKind.CANCELLED)

    query.update({UserActiveRoute.cancelled_reason: reason}, synchronize_session=False)

    return len(user_ids)


def users_doing(db: Session, route_id: int) -> int:
    """Quantos usuários estão fazendo a rota agora (aviso no painel)."""
    return (
        db.query(UserActiveRoute)
        .filter(
            UserActiveRoute.route_id == route_id,
            UserActiveRoute.cancelled_reason.is_(None),
        )
        .count()
    )


def point_status(index: int, next_index: int) -> str:
    if index < next_index:
        return DONE
    if index == next_index:
        return CURRENT
    return PENDING
