from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.controller.serializers import serialize_badge_full, serialize_collected
from app.core.dependencies import get_current_user
from app.core.rate_limit import RateLimiter, format_wait, too_many_requests
from app.database.database import get_db
from app.model.badge import Badge, BadgeRule
from app.model.email_code import EmailCode
from app.model.mupi_object import MupiObject
from app.model.user import User
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit
from app.service import storage_service
from app.service.auth_service import password_hash, revoke_sessions
from app.service.badge_service import award_badges, progress_of, visit_counts

router = APIRouter(
    prefix="/users",
    tags=["Usuários"]
)

# As visitas e as insígnias acontecem ao abrir o ponto
# (POST /mupi-objects/{id}/open). As rotas antigas POST /users/me/visits
# (check-in) e POST /users/me/badges (coleta manual) foram removidas (INS-02).


def _award_retroactive(db: Session, user_id: int) -> None:
    """Concede insígnias criadas depois que o usuário já cumpria a condição
    (INS-06): ex.: "Visitar 3 pontos" criada quando ele já tinha 5 visitas."""
    try:
        if award_badges(db, user_id):
            db.commit()
    except IntegrityError:
        # Outra requisição concedeu ao mesmo tempo: o perfil mostra a dela
        db.rollback()


# ---------- Perfil (USR-07, INS-08) ----------

@router.get("/me")
def get_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = user.id
    _award_retroactive(db, user_id)

    collected = (
        db.query(UserBadge)
        .options(
            selectinload(UserBadge.badge).selectinload(Badge.theme),
            selectinload(UserBadge.mupi_object),
        )
        .filter(UserBadge.user_id == user_id)
        .order_by(UserBadge.collected_at.desc())
        .all()
    )

    visits_total, by_theme = visit_counts(db, user_id)

    collected_ids = (
        db.query(UserBadge.badge_id)
        .filter(UserBadge.user_id == user_id)
    )

    not_collected = (
        db.query(Badge)
        .options(selectinload(Badge.theme))
        .filter(Badge.active.is_(True), Badge.id.notin_(collected_ids))
        .order_by(Badge.required_count, Badge.name)
        .all()
    )

    # Em progresso: as de quantidade, com o quanto falta (ex.: 3 de 5)
    in_progress = [
        {
            **serialize_badge_full(badge),
            "progress": min(
                progress_of(badge, visits_total, by_theme),
                badge.required_count
            ),
        }
        for badge in not_collected
        if badge.rule_type != BadgeRule.POINT_VISIT
    ]

    # Bloqueadas: as de visita a ponto ainda não ganhas. Vão sem nome,
    # descrição nem imagem, para não revelar o ponto: o app mostra uma
    # silhueta (INS-08)
    locked = [
        {"id": badge.id, "type": badge.rule_type.value}
        for badge in not_collected
        if badge.rule_type == BadgeRule.POINT_VISIT
    ]

    # Total possível: as ativas, mais as desativadas que ele já tem
    # (essas só aparecem para quem as conquistou)
    active_total = (
        db.query(func.count(Badge.id))
        .filter(Badge.active.is_(True))
        .scalar()
    ) or 0

    inactive_collected = sum(1 for item in collected if not item.badge.active)

    return {
        "id": user.id,
        "email": user.email,
        "created_at": user.created_at.isoformat(),
        "visits_total": visits_total,
        "badges_collected": len(collected),
        "badges_total": active_total + inactive_collected,
        "badges": [serialize_collected(item) for item in collected],
        "in_progress": in_progress,
        "locked": locked,
        # Rota que o usuário está fazendo (Etapa 5, ROT-04)
        "active_route": None,
    }


# ---------- Histórico de visitas (VIS-04) ----------

@router.get("/me/visits")
def get_visits(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pontos visitados, do mais recente ao mais antigo.

    Inclui os pontos hoje desativados, marcados como indisponíveis, para o
    histórico não "sumir".
    """
    rows = (
        db.query(UserVisit, MupiObject)
        .join(MupiObject, MupiObject.id == UserVisit.object_id)
        .filter(UserVisit.user_id == user.id)
        .order_by(UserVisit.visited_at.desc(), MupiObject.name)
        .all()
    )

    return [
        {
            "id": point.id,
            "name": point.name,
            "photo_url": storage_service.url(point.photo_key),
            "visited_at": visit.visited_at.isoformat(),
            "available": point.active,
        }
        for visit, point in rows
    ]


# ---------- Exclusão de conta (USR-08) ----------

# Senha errada: no máximo 5 tentativas a cada 15 min por conta. Com um
# celular desbloqueado nas mãos, alguém poderia tentar adivinhar a senha
DELETE_ATTEMPTS = 5
DELETE_WINDOW_SECONDS = 15 * 60
delete_account_limiter = RateLimiter(DELETE_ATTEMPTS, DELETE_WINDOW_SECONDS)


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


@router.delete("/me")
def delete_account(
    data: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exclui a conta de vez: usuário, visitas, insígnias conquistadas e
    códigos de e-mail pendentes. Todos os tokens deixam de valer.

    Pede a senha atual. Quando houver login com Google (contas sem senha),
    elas vão confirmar com um id_token recente do Google.
    """
    user_id = user.id

    wait = delete_account_limiter.retry_after(user_id)

    if wait:
        raise too_many_requests(
            wait,
            f"Muitas tentativas. Aguarde {format_wait(wait)} e tente novamente."
        )

    if not password_hash.verify(data.password, user.password_hash):
        delete_account_limiter.record(user_id)
        # 403, e não 401: o app trata 401 como sessão expirada
        raise HTTPException(status_code=403, detail="Senha incorreta.")

    # Os tokens deixam de valer mesmo que algo guarde o usuário em cache
    revoke_sessions(user)

    db.query(EmailCode).filter(EmailCode.email == user.email).delete()
    # Visitas e conquistas saem junto (ON DELETE CASCADE no banco)
    db.delete(user)
    db.commit()

    delete_account_limiter.forget(user_id)

    return {"message": "Sua conta foi excluída."}
