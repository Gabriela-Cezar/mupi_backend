"""Telas de insígnias do painel (ADM-06, ADM-08, ADM-09, ADM-12).

- lista: /admin/badges
- cadastro: /admin/badges/new
- edição: /admin/badges/{id}/edit
- ativar/desativar: POST /admin/badges/{id}/status
- excluir (com confirmação): /admin/badges/{id}/delete

Insígnia já conquistada não muda de regra (tipo, ponto, tema ou quantidade):
quem a ganhou ganhou por aquela regra. Para outra regra, cria-se outra
insígnia (e desativa-se esta, se for o caso).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.controller.admin_files import (
    commit_or_delete_files,
    read_image,
    store_file,
    uploaded_file,
)
from app.controller.badge_form import (
    RULE_LABELS,
    BadgeDraft,
    apply_badge,
    condition_of,
    draft_from_badge,
    read_badge_form,
    validate_badge,
)
from app.controller.mupi_object_form import FormError
from app.core.admin_auth import require_admin_with_csrf
from app.core.admin_messages import with_message
from app.core.templates import templates
from app.database.database import get_db
from app.model.badge import Badge
from app.model.mupi_object import MupiObject
from app.model.theme import Theme
from app.model.user_badge import UserBadge
from app.service import storage_service

LIST_URL = "/admin/badges"

router = APIRouter(
    prefix=LIST_URL,
    tags=["Administração - Insígnias"],
    dependencies=[Depends(require_admin_with_csrf)]
)


def _redirect(code: str) -> RedirectResponse:
    return RedirectResponse(with_message(LIST_URL, code), status_code=303)


def _get_badge(db: Session, badge_id: int) -> Badge:
    badge = db.get(Badge, badge_id)

    if badge is None:
        raise HTTPException(status_code=404, detail="Insígnia não encontrada.")

    return badge


def _collected_count(db: Session, badge_id: int) -> int:
    return (
        db.query(func.count(UserBadge.user_id))
        .filter(UserBadge.badge_id == badge_id)
        .scalar()
    ) or 0


# ---------- Lista ----------

@router.get("")
def list_badges(request: Request, db: Session = Depends(get_db)):
    badges = (
        db.query(Badge)
        .options(selectinload(Badge.mupi_object), selectinload(Badge.theme))
        .order_by(Badge.name)
        .all()
    )

    collected = dict(
        db.query(UserBadge.badge_id, func.count())
        .group_by(UserBadge.badge_id)
        .all()
    )

    rows = [
        {
            "badge": badge,
            "type": RULE_LABELS[badge.rule_type],
            "condition": condition_of(badge),
            "image_url": storage_service.url(badge.image_key),
            "collected": collected.get(badge.id, 0),
        }
        for badge in badges
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin/badge_list.html",
        context={"rows": rows},
    )


# ---------- Formulário (cadastro e edição) ----------

def _render_form(
    request: Request,
    db: Session,
    draft: BadgeDraft,
    badge_id: int | None = None,
    collected: int = 0,
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="admin/badge_form.html",
        context={
            "badge": draft,
            "editing": badge_id is not None,
            "form_action": f"{LIST_URL}/{badge_id}/edit" if badge_id else LIST_URL,
            "image_url": storage_service.url(draft.image_key),
            # Já conquistada: a regra não muda (ver a docstring do módulo)
            "rule_locked": collected > 0,
            "collected": collected,
            "rules": [(rule.value, label) for rule, label in RULE_LABELS.items()],
            "points": db.query(MupiObject).order_by(MupiObject.name).all(),
            "themes": db.query(Theme).order_by(Theme.name).all(),
            "error": error,
        },
        status_code=status_code,
    )


async def _read_image(request: Request) -> tuple[bytes, str] | None:
    image = await uploaded_file(request, "image")

    if image is None:
        return None

    try:
        return read_image(image)
    except HTTPException as exc:
        raise FormError(exc.detail, exc.status_code)


@router.get("/new")
def new_badge_form(request: Request, db: Session = Depends(get_db)):
    return _render_form(request, db, BadgeDraft())


@router.post("")
async def create_badge(request: Request, db: Session = Depends(get_db)):
    draft = read_badge_form(await request.form())

    try:
        data = validate_badge(db, draft)
        image = await _read_image(request)
    except FormError as exc:
        return _render_form(request, db, draft, error=exc.message, status_code=exc.status_code)

    badge = Badge()
    apply_badge(badge, data)
    db.add(badge)

    try:
        # Gera o id da insígnia, usado no caminho da imagem no S3
        db.flush()
    except IntegrityError:
        db.rollback()
        return _render_form(
            request, db, draft,
            error="Já existe uma insígnia com esse nome.", status_code=400,
        )

    sent = []

    if image is not None:
        try:
            badge.image_key = store_file(db, f"badges/{badge.id}", "image", *image)
        except HTTPException as exc:
            # store_file já desfez o que estava pendente no banco
            return _render_form(
                request, db, draft, error=exc.detail, status_code=exc.status_code
            )
        sent.append(badge.image_key)

    commit_or_delete_files(db, sent)

    return _redirect("badge-created")


@router.get("/{badge_id}/edit")
def edit_badge_form(badge_id: int, request: Request, db: Session = Depends(get_db)):
    badge = _get_badge(db, badge_id)

    return _render_form(
        request, db, draft_from_badge(badge),
        badge_id=badge.id, collected=_collected_count(db, badge.id),
    )


@router.post("/{badge_id}/edit")
async def update_badge(badge_id: int, request: Request, db: Session = Depends(get_db)):
    badge = _get_badge(db, badge_id)
    collected = _collected_count(db, badge.id)

    draft = read_badge_form(await request.form())
    draft.image_key = badge.image_key

    if collected:
        # O formulário mostra a regra salva, que não muda
        saved = draft_from_badge(badge)
        draft.rule_type, draft.object_id = saved.rule_type, saved.object_id
        draft.theme_id, draft.required_count = saved.theme_id, saved.required_count

    def error(message: str, status_code: int):
        return _render_form(
            request, db, draft, badge_id=badge_id, collected=collected,
            error=message, status_code=status_code,
        )

    try:
        data = validate_badge(db, draft, badge=badge, rule_locked=collected > 0)
        image = await _read_image(request)
    except FormError as exc:
        return error(exc.message, exc.status_code)

    old_key = badge.image_key
    apply_badge(badge, data)
    sent = []

    if image is not None:
        # Substituir a imagem apaga a anterior
        try:
            badge.image_key = store_file(db, f"badges/{badge.id}", "image", *image)
        except HTTPException as exc:
            return error(exc.detail, exc.status_code)
        sent.append(badge.image_key)
    elif draft.remove_image:
        badge.image_key = None

    try:
        commit_or_delete_files(db, sent)
    except IntegrityError:
        return error("Já existe uma insígnia com esse nome.", 400)

    if old_key and old_key != badge.image_key:
        storage_service.delete_quietly(old_key)

    return _redirect("badge-updated")


# ---------- Ativar e desativar (ADM-08) ----------

@router.post("/{badge_id}/status")
async def set_badge_status(badge_id: int, request: Request, db: Session = Depends(get_db)):
    badge = _get_badge(db, badge_id)
    form = await request.form()

    badge.active = str(form.get("active", "")).lower() == "true"
    db.commit()

    return _redirect("badge-activated" if badge.active else "badge-deactivated")


# ---------- Excluir (ADM-09) ----------

def delete_blockers(db: Session, badge: Badge) -> list[str]:
    """Insígnia já conquistada não pode ser excluída: a conquista continua com
    o usuário (FAL-11). O painel oferece desativar. Vazio = pode excluir."""
    collected = _collected_count(db, badge.id)

    if collected == 1:
        return ["1 usuário já conquistou esta insígnia."]

    if collected:
        return [f"{collected} usuários já conquistaram esta insígnia."]

    return []


def _render_delete(
    request: Request,
    badge: Badge,
    blockers: list[str],
    status_code: int = 200,
):
    consequences = []

    if badge.image_key:
        consequences.append("A imagem é apagada do armazenamento.")

    return templates.TemplateResponse(
        request=request,
        name="admin/confirm_delete.html",
        context={
            "title": "Excluir insígnia",
            "item_name": badge.name,
            "blockers": blockers,
            "consequences": consequences,
            "delete_action": f"{LIST_URL}/{badge.id}/delete",
            "cancel_url": LIST_URL,
            "deactivate_action": f"{LIST_URL}/{badge.id}/status" if badge.active else None,
        },
        status_code=status_code,
    )


@router.get("/{badge_id}/delete")
def confirm_delete_badge(badge_id: int, request: Request, db: Session = Depends(get_db)):
    badge = _get_badge(db, badge_id)

    return _render_delete(request, badge, delete_blockers(db, badge))


@router.post("/{badge_id}/delete")
def delete_badge(badge_id: int, request: Request, db: Session = Depends(get_db)):
    badge = _get_badge(db, badge_id)
    blockers = delete_blockers(db, badge)

    if blockers:
        return _render_delete(request, badge, blockers, status_code=409)

    image_key = badge.image_key
    db.delete(badge)

    try:
        db.commit()
    except IntegrityError:
        # Alguém conquistou a insígnia entre a conferência e a exclusão
        db.rollback()
        badge = _get_badge(db, badge_id)
        return _render_delete(
            request, badge,
            delete_blockers(db, badge) or ["A insígnia tem histórico de uso."],
            status_code=409,
        )

    storage_service.delete_quietly(image_key)

    return _redirect("badge-deleted")

