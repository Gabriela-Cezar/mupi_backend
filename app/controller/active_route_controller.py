"""Rota ativa do usuário (ROT-06 a ROT-10), sempre com login.

- GET    /users/me/active-route                          — ver (com o aviso do ROT-10)
- POST   /users/me/active-route/points/{id}/finish       — finalizar o ponto atual
- POST   /users/me/active-route/complete                 — encerrar a rota concluída
- DELETE /users/me/active-route                          — abandonar

- POST   /routes/{id}/start                              — iniciar (ROT-05)
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.controller.route_controller import serialize_route_detail, serialize_route_summary
from app.core.dependencies import get_current_user
from app.database.database import get_db
from app.model.route import Route
from app.model.user import User
from app.model.user_active_route import UserActiveRoute
from app.model.user_route_completion import UserRouteCompletion
from app.model.user_visit import UserVisit
from app.controller.serializers import serialize_collected
from app.model.route_event import RouteEventKind
from app.service.active_route_service import NOTICES, get_progress, point_status, record_event
from app.service.badge_service import award_badges
from app.service.route_point_content_service import contents_for_route
from app.service.proximity_service import get_mupi_in_range

router = APIRouter(
    prefix="/users/me/active-route",
    tags=["Rota ativa"],
    dependencies=[Depends(get_current_user)],
)

start_router = APIRouter(
    prefix="/routes",
    tags=["Rota ativa"],
    dependencies=[Depends(get_current_user)],
)


def _visited(db: Session, user_id: int) -> set[int]:
    return {
        object_id for (object_id,) in
        db.query(UserVisit.object_id).filter(UserVisit.user_id == user_id)
    }


def _completed(db: Session, user_id: int, route_id: int) -> bool:
    return db.query(UserRouteCompletion.id).filter(
        UserRouteCompletion.user_id == user_id,
        UserRouteCompletion.route_id == route_id,
    ).first() is not None


def serialize_active_route(db: Session, progress: UserActiveRoute) -> dict:
    """A rota com o estado de cada ponto e o trecho atual (ROT-06)."""
    route = progress.route
    next_index = progress.next_index
    total = len(route.points)

    data = serialize_route_detail(
        route,
        _completed(db, progress.user_id, route.id),
        _visited(db, progress.user_id),
        contents_for_route(db, route.id),
    )

    for index, point in enumerate(data["points"]):
        point["status"] = point_status(index, next_index)

    next_point = data["points"][next_index] if next_index < total else None

    return {
        "route": data,
        "started_at": progress.started_at.isoformat(),
        "next_index": next_index,
        "next_point": {"id": next_point["id"], "name": next_point["name"]} if next_point else None,
        # Trecho do ponto anterior ao atual (índice em route.waypoints). No
        # primeiro ponto não há trecho: o app usa o "Como chegar"
        "current_leg": next_index - 1 if 0 < next_index < total else None,
        "all_finished": next_index >= total,
    }


def active_route_or_none(db: Session, user_id: int) -> dict | None:
    """Rota ativa para o perfil (GET /users/me); sem o aviso do ROT-10."""
    progress = get_progress(db, user_id)

    if progress is None or progress.cancelled_reason:
        return None

    return serialize_active_route(db, progress)


def _require_progress(db: Session, user: User) -> UserActiveRoute:
    progress = get_progress(db, user.id)

    if progress is None:
        raise HTTPException(status_code=404, detail="Você não está fazendo nenhuma rota.")

    if progress.cancelled_reason:
        message = NOTICES.get(progress.cancelled_reason, "Esta rota foi encerrada.")
        db.delete(progress)
        db.commit()
        raise HTTPException(status_code=409, detail=message)

    return progress


# ---------- Iniciar (ROT-05) ----------

@start_router.post("/{route_id}/start")
def start_route(route_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Uma rota ativa por vez. Com outra em andamento, responde 409 dizendo
    qual: o app pergunta se o usuário quer abandoná-la e iniciar esta.
    Refazer uma rota já concluída é permitido."""
    route = db.get(Route, route_id)

    if route is None or not route.active or not route.has_path:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")

    progress = db.get(UserActiveRoute, user.id)

    if progress is not None:
        if progress.cancelled_reason:
            # A anterior foi encerrada pelo administrador: pode começar outra
            db.delete(progress)
            db.flush()
        elif progress.route_id == route.id:
            # Já está fazendo esta: devolve o progresso, sem recomeçar
            return {"active_route": serialize_active_route(db, get_progress(db, user.id)), "notice": None}
        else:
            active = db.get(Route, progress.route_id)
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        f"Você está fazendo a rota {active.name}. "
                        "Abandone-a para iniciar esta (o progresso dela será perdido)."
                    ),
                    "active_route": {"id": active.id, "name": active.name},
                },
            )

    db.add(UserActiveRoute(user_id=user.id, route_id=route.id, next_index=0))
    record_event(db, user.id, route.id, RouteEventKind.STARTED)

    try:
        db.commit()
    except IntegrityError:
        # Dois "iniciar" ao mesmo tempo: o outro chegou primeiro
        db.rollback()
        raise HTTPException(status_code=409, detail="Você já está fazendo uma rota.")

    return {"active_route": serialize_active_route(db, get_progress(db, user.id)), "notice": None}


# ---------- Ver (ROT-06) ----------

@router.get("")
def get_active_route(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    progress = get_progress(db, user.id)

    if progress is None:
        return {"active_route": None, "notice": None}

    if progress.cancelled_reason:
        # Encerrada pelo administrador (ROT-10): avisa uma vez e apaga
        notice = NOTICES.get(progress.cancelled_reason, "Esta rota foi encerrada.")
        db.delete(progress)
        db.commit()
        return {"active_route": None, "notice": notice}

    return {"active_route": serialize_active_route(db, progress), "notice": None}


# ---------- Finalizar ponto (ROT-07) ----------

class FinishPointRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=100_000)


@router.post("/points/{object_id}/finish")
def finish_point(
    object_id: int,
    data: FinishPointRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    progress = _require_progress(db, user)
    route = progress.route
    ids = route.point_ids
    current = progress.next_index

    # 1. Só o próximo ponto da sequência
    if object_id not in ids:
        raise HTTPException(status_code=409, detail="Este ponto não faz parte da rota.")

    index = ids.index(object_id)

    if index < current:
        raise HTTPException(status_code=409, detail="Este ponto já foi finalizado.")

    if index > current:
        name = route.points[current].mupi_object.name
        raise HTTPException(
            status_code=409,
            detail=f"Finalize os pontos na ordem: o próximo é {name}.",
        )

    # 2. O ponto precisa ter sido aberto (a visita existe)
    if db.get(UserVisit, (user.id, object_id)) is None:
        raise HTTPException(status_code=409, detail="Abra o ponto antes de finalizar.")

    # 3. Perto do ponto agora (mesma regra da abertura)
    get_mupi_in_range(
        db, object_id, data.latitude, data.longitude, data.accuracy, user_id=user.id
    )

    # Avança só se ainda estiver neste ponto: dois toques juntos não pulam um
    advanced = (
        db.query(UserActiveRoute)
        .filter(
            UserActiveRoute.user_id == user.id,
            UserActiveRoute.next_index == current,
            UserActiveRoute.cancelled_reason.is_(None),
        )
        .update({UserActiveRoute.next_index: current + 1}, synchronize_session=False)
    )
    db.commit()

    if not advanced:
        raise HTTPException(status_code=409, detail="Este ponto já foi finalizado.")

    db.expire_all()
    return {"active_route": serialize_active_route(db, get_progress(db, user.id)), "notice": None}


# ---------- Encerrar (ROT-08) ----------

@router.post("/complete")
def complete_route(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    progress = _require_progress(db, user)
    route = progress.route

    if progress.next_index < len(route.points):
        raise HTTPException(
            status_code=409,
            detail="Finalize todos os pontos antes de encerrar a rota.",
        )

    db.add(UserRouteCompletion(user_id=user.id, route_id=route.id))
    db.delete(progress)
    record_event(db, user.id, route.id, RouteEventKind.COMPLETED)
    db.flush()

    # Insígnia de conclusão desta rota, uma vez só (INS-04, INS-09)
    awarded = award_badges(db, user.id)
    awarded_data = [serialize_collected(item) for item in awarded]
    db.commit()

    completions = (
        db.query(func.count(UserRouteCompletion.id))
        .filter(
            UserRouteCompletion.user_id == user.id,
            UserRouteCompletion.route_id == route.id,
        )
        .scalar()
    )

    return {
        "route": serialize_route_summary(route, completed=True),
        "completions": completions,
        "awarded": awarded_data,
    }


# ---------- Abandonar (ROT-09) ----------

@router.delete("")
def abandon_route(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    progress = get_progress(db, user.id)

    if progress is None:
        raise HTTPException(status_code=404, detail="Você não está fazendo nenhuma rota.")

    # As visitas feitas durante a rota continuam valendo
    if not progress.cancelled_reason:
        record_event(db, user.id, progress.route_id, RouteEventKind.ABANDONED)
    db.delete(progress)
    db.commit()

    return {"message": "Rota abandonada."}
