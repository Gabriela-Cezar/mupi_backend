import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.controller.active_route_controller import active_route_or_none
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
from app.service.auth_service import check_password, revoke_sessions
from app.service.google_auth_service import (
    GoogleLoginDisabled,
    GoogleTokenError,
    verify_google_token,
)
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
            selectinload(UserBadge.route),
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
        if badge.rule_type in (BadgeRule.VISIT_COUNT, BadgeRule.THEME_VISIT_COUNT)
    ]

    # Bloqueadas: as de visita a ponto e de conclusão de rota ainda não
    # ganhas. Vão sem nome, descrição nem imagem, para não revelar o ponto
    # ou a rota: o app mostra uma silhueta (INS-08)
    locked = [
        {"id": badge.id, "type": badge.rule_type.value}
        for badge in not_collected
        if badge.rule_type in (BadgeRule.POINT_VISIT, BadgeRule.ROUTE_COMPLETION)
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
        # Rota que o usuário está fazendo (USR-07, ROT-06)
        "active_route": active_route_or_none(db, user_id),
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


# Confirmação pelo Google: o id_token tem de ser recente (o usuário acabou de
# entrar com o Google para confirmar), não um guardado de dias atrás
GOOGLE_CONFIRM_MAX_AGE_SECONDS = 10 * 60


class DeleteAccountRequest(BaseModel):
    # Conta com senha: a senha atual
    password: str | None = Field(default=None, min_length=1, max_length=128)
    # Conta com Google: um id_token recente (USR-08)
    id_token: str | None = Field(default=None, min_length=1, max_length=8192)


def _confirmed(user: User, data: DeleteAccountRequest) -> bool:
    """A senha confere, ou o id_token é desta conta Google e é recente."""
    if data.password is not None:
        return check_password(user.password_hash, data.password)

    if user.google_sub is None:
        return False

    try:
        identity = verify_google_token(data.id_token)
    except (GoogleTokenError, GoogleLoginDisabled):
        return False

    recent = time.time() - identity.issued_at <= GOOGLE_CONFIRM_MAX_AGE_SECONDS
    return identity.sub == user.google_sub and recent


@router.delete("/me")
def delete_account(
    data: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exclui a conta de vez: usuário, visitas, insígnias conquistadas,
    progresso e conclusões de rota e códigos de e-mail pendentes. Todos os
    tokens deixam de valer.

    Confirmação: a senha atual, ou (conta com Google) um id_token recente do
    Google, obtido entrando com o Google de novo.
    """
    user_id = user.id

    if data.password is None and data.id_token is None:
        raise HTTPException(
            status_code=422,
            detail="Confirme com a sua senha ou entrando com o Google.",
        )

    wait = delete_account_limiter.retry_after(user_id)

    if wait:
        raise too_many_requests(
            wait,
            f"Muitas tentativas. Aguarde {format_wait(wait)} e tente novamente."
        )

    if not _confirmed(user, data):
        delete_account_limiter.record(user_id)
        # 403, e não 401: o app trata 401 como sessão expirada
        detail = (
            "Senha incorreta." if data.password is not None
            else "Não foi possível confirmar com o Google. Entre com o Google de novo."
        )
        raise HTTPException(status_code=403, detail=detail)

    # Os tokens deixam de valer mesmo que algo guarde o usuário em cache
    revoke_sessions(user)

    db.query(EmailCode).filter(EmailCode.email == user.email).delete()
    # Visitas, conquistas e rotas saem junto (ON DELETE CASCADE no banco)
    db.delete(user)
    db.commit()

    delete_account_limiter.forget(user_id)

    return {"message": "Sua conta foi excluída."}


# ---------- Sair de todos os aparelhos (USR-13) ----------

@router.post("/me/logout-all")
def logout_everywhere(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Encerra todas as sessões da conta, inclusive a deste aparelho: útil
    quando o celular foi perdido ou alguém pode ter a senha."""
    revoke_sessions(user)
    db.commit()

    return {"message": "Você saiu de todos os aparelhos."}
