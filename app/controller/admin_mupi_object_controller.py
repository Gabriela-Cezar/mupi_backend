"""Telas de pontos MUPI do painel (ADM-04, ADM-08, ADM-09, ADM-12).

- lista: /admin/mupi-objects
- cadastro: /admin/mupi-objects/new
- edição: /admin/mupi-objects/{id}/edit
- ativar/desativar: POST /admin/mupi-objects/{id}/status
- excluir (com confirmação): /admin/mupi-objects/{id}/delete

Depois de salvar, volta para a lista com uma mensagem. Com erro, mostra o
formulário de novo com a mensagem e o que foi digitado.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.controller.admin_files import (
    commit_or_delete_files,
    read_audio,
    read_image,
    store_file,
    uploaded_file,
)
from app.controller.mupi_object_form import (
    FormError,
    PointDraft,
    apply_point,
    draft_from_point,
    read_point_form,
    validate_point,
)
from app.core.admin_auth import require_admin_with_csrf
from app.core.admin_messages import with_message
from app.core.templates import templates
from app.database.database import get_db
from app.model.badge import Badge
from app.model.mupi_object import MupiObject
from app.model.theme import Theme
from app.model.user_visit import UserVisit
from app.service import storage_service

LIST_URL = "/admin/mupi-objects"

router = APIRouter(
    prefix=LIST_URL,
    tags=["Administração - Pontos"],
    dependencies=[Depends(require_admin_with_csrf)]
)


def _redirect(code: str) -> RedirectResponse:
    return RedirectResponse(with_message(LIST_URL, code), status_code=303)


def _get_point(db: Session, point_id: int) -> MupiObject:
    point = db.get(MupiObject, point_id)

    if point is None:
        raise HTTPException(status_code=404, detail="Ponto não encontrado.")

    return point


def _visit_counts(db: Session) -> dict[int, int]:
    return dict(
        db.query(UserVisit.object_id, func.count())
        .group_by(UserVisit.object_id)
        .all()
    )


# ---------- Lista ----------

@router.get("")
def list_points(request: Request, db: Session = Depends(get_db)):
    points = (
        db.query(MupiObject)
        .options(selectinload(MupiObject.themes), selectinload(MupiObject.badges))
        .order_by(MupiObject.name)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/mupi_object_list.html",
        context={"points": points, "visits": _visit_counts(db)},
    )


# ---------- Formulário (cadastro e edição) ----------

def _render_form(
    request: Request,
    db: Session,
    draft: PointDraft,
    point_id: int | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    # Insígnias de visita deste ponto (a ligação é feita na insígnia)
    badges = (
        db.query(Badge)
        .filter(Badge.object_id == point_id)
        .order_by(Badge.name)
        .all()
        if point_id is not None else []
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/mupi_object_form.html",
        context={
            "point": draft,
            "editing": point_id is not None,
            "form_action": f"{LIST_URL}/{point_id}/edit" if point_id else LIST_URL,
            "photo_url": storage_service.url(draft.photo_key),
            "audio_url": storage_service.url(
                draft.audio_key, storage_service.AUDIO_URL_SECONDS
            ),
            "themes": db.query(Theme).order_by(Theme.name).all(),
            "badges": badges,
            "error": error,
        },
        status_code=status_code,
    )


async def _read_photo(request: Request) -> tuple[bytes, str] | None:
    photo = await uploaded_file(request, "photo")

    if photo is None:
        return None

    try:
        return read_image(photo)
    except HTTPException as exc:
        raise FormError(exc.detail, exc.status_code)


async def _read_audio(request: Request) -> tuple[bytes, str, int] | None:
    audio = await uploaded_file(request, "audio")

    if audio is None:
        return None

    try:
        return read_audio(audio)
    except HTTPException as exc:
        raise FormError(exc.detail, exc.status_code)


def _store_files(
    db: Session,
    point: MupiObject,
    photo: tuple[bytes, str] | None,
    audio: tuple[bytes, str, int] | None,
) -> list[str]:
    """Envia a foto e o áudio novos ao S3 e guarda as chaves no ponto.

    Devolve as chaves enviadas. Se um envio falhar, apaga o que já tinha ido
    (store_file desfaz o banco) e repassa o erro.
    """
    sent: list[str] = []
    prefix = f"points/{point.id}"

    try:
        if photo is not None:
            point.photo_key = store_file(db, prefix, "photo", *photo)
            sent.append(point.photo_key)

        if audio is not None:
            data, mime_type, duration = audio
            point.audio_key = store_file(db, prefix, "audio", data, mime_type)
            point.audio_duration = duration
            sent.append(point.audio_key)
    except HTTPException:
        for key in sent:
            storage_service.delete_quietly(key)
        raise

    return sent


@router.get("/new")
def new_point_form(request: Request, db: Session = Depends(get_db)):
    return _render_form(request, db, PointDraft())


@router.post("")
async def create_point(request: Request, db: Session = Depends(get_db)):
    draft = read_point_form(await request.form())

    try:
        data = validate_point(db, draft)
        photo = await _read_photo(request)
        audio = await _read_audio(request)
    except FormError as exc:
        return _render_form(request, db, draft, error=exc.message, status_code=exc.status_code)

    point = MupiObject()
    apply_point(point, data)
    db.add(point)
    # Gera o id do ponto, usado no caminho dos arquivos no S3
    db.flush()

    try:
        sent = _store_files(db, point, photo, audio)
    except HTTPException as exc:
        # store_file já desfez o que estava pendente no banco
        return _render_form(
            request, db, draft, error=exc.detail, status_code=exc.status_code
        )

    commit_or_delete_files(db, sent)

    return _redirect("point-created")


@router.get("/{point_id}/edit")
def edit_point_form(point_id: int, request: Request, db: Session = Depends(get_db)):
    point = _get_point(db, point_id)

    return _render_form(request, db, draft_from_point(point), point_id=point.id)


@router.post("/{point_id}/edit")
async def update_point(point_id: int, request: Request, db: Session = Depends(get_db)):
    point = _get_point(db, point_id)
    draft = read_point_form(await request.form())
    draft.photo_key = point.photo_key
    draft.audio_key = point.audio_key
    draft.audio_duration = point.audio_duration

    try:
        data = validate_point(db, draft)
        photo = await _read_photo(request)
        audio = await _read_audio(request)
    except FormError as exc:
        return _render_form(
            request, db, draft, point_id=point.id,
            error=exc.message, status_code=exc.status_code,
        )

    old_keys = {point.photo_key, point.audio_key}
    apply_point(point, data)

    try:
        sent = _store_files(db, point, photo, audio)
    except HTTPException as exc:
        return _render_form(
            request, db, draft, point_id=point_id,
            error=exc.detail, status_code=exc.status_code,
        )

    # Remover só vale quando não veio um arquivo novo no lugar
    if photo is None and draft.remove_photo:
        point.photo_key = None

    if audio is None and draft.remove_audio:
        point.audio_key = None
        point.audio_duration = None

    commit_or_delete_files(db, sent)

    # Substituir ou remover apaga o arquivo anterior (PT-05, PT-06)
    for key in old_keys - {point.photo_key, point.audio_key, None}:
        storage_service.delete_quietly(key)

    return _redirect("point-updated")


# ---------- Ativar e desativar (ADM-08) ----------

@router.post("/{point_id}/status")
async def set_point_status(point_id: int, request: Request, db: Session = Depends(get_db)):
    point = _get_point(db, point_id)
    form = await request.form()

    point.active = str(form.get("active", "")).lower() == "true"
    db.commit()

    return _redirect("point-activated" if point.active else "point-deactivated")


# ---------- Excluir (ADM-09) ----------

def delete_blockers(db: Session, point: MupiObject) -> list[str]:
    """Motivos que impedem excluir o ponto. Vazio = pode excluir.

    Ponto com histórico (visitas) ou ligado a insígnia não pode ser
    excluído: a insígnia e o histórico continuam com o usuário. O painel
    oferece desativar. Rotas entram na Etapa 5.
    """
    reasons = []

    visits = db.query(UserVisit).filter(UserVisit.object_id == point.id).count()

    if visits:
        reasons.append(
            f"{visits} usuário(s) já visitaram este ponto." if visits > 1
            else "1 usuário já visitou este ponto."
        )

    badge_names = [
        name for (name,) in db.query(Badge.name)
        .filter(Badge.object_id == point.id)
        .order_by(Badge.name)
    ]

    if badge_names:
        reasons.append("Está ligado à insígnia: " + ", ".join(badge_names) + ".")

    return reasons


def _render_delete(
    request: Request,
    point: MupiObject,
    blockers: list[str],
    status_code: int = 200,
):
    consequences = ["Os blocos de texto e os vídeos do ponto também são apagados."]

    if point.photo_key:
        consequences.append("A foto é apagada do armazenamento.")

    if point.audio_key:
        consequences.append("O áudio é apagado do armazenamento.")

    return templates.TemplateResponse(
        request=request,
        name="admin/confirm_delete.html",
        context={
            "title": "Excluir ponto",
            "item_name": point.name,
            "blockers": blockers,
            "consequences": consequences,
            "delete_action": f"{LIST_URL}/{point.id}/delete",
            "cancel_url": LIST_URL,
            "deactivate_action": f"{LIST_URL}/{point.id}/status" if point.active else None,
        },
        status_code=status_code,
    )


@router.get("/{point_id}/delete")
def confirm_delete_point(point_id: int, request: Request, db: Session = Depends(get_db)):
    point = _get_point(db, point_id)

    return _render_delete(request, point, delete_blockers(db, point))


@router.post("/{point_id}/delete")
def delete_point(point_id: int, request: Request, db: Session = Depends(get_db)):
    point = _get_point(db, point_id)
    blockers = delete_blockers(db, point)

    if blockers:
        return _render_delete(request, point, blockers, status_code=409)

    file_keys = [point.photo_key, point.audio_key]
    db.delete(point)

    try:
        db.commit()
    except IntegrityError:
        # Alguém visitou o ponto entre a conferência e a exclusão
        db.rollback()
        point = _get_point(db, point_id)
        return _render_delete(
            request, point,
            delete_blockers(db, point) or ["O ponto tem histórico de uso."],
            status_code=409,
        )

    for key in file_keys:
        storage_service.delete_quietly(key)

    return _redirect("point-deleted")
