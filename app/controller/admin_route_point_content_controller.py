"""Conteúdo de um ponto dentro de uma rota, no painel.

- GET/POST /admin/routes/{rota}/points/{ponto}/content — editar;
- POST /admin/routes/{rota}/points/{ponto}/content/delete — voltar a usar o
  conteúdo normal do ponto nesta rota.

Quem abre o ponto fazendo a rota vê este conteúdo no lugar do do ponto.
Mudar o conteúdo não mexe no progresso de quem está fazendo a rota.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.controller.admin_files import (
    commit_or_delete_files,
    read_audio,
    read_image,
    store_file,
    uploaded_file,
)
from app.controller.mupi_object_form import FormError
from app.controller.route_point_content_form import (
    ContentDraft,
    apply_content,
    draft_from_content,
    draft_from_point,
    read_content_form,
    validate_content,
)
from app.core.admin_auth import require_admin_with_csrf
from app.core.admin_messages import with_message
from app.core.templates import templates
from app.database.database import get_db
from app.model.mupi_object import MupiObject
from app.model.route import Route
from app.model.route_point_content import RoutePointContent
from app.service import storage_service
from app.service.route_point_content_service import get_content

router = APIRouter(
    prefix="/admin/routes/{route_id}/points/{object_id}/content",
    tags=["Administração - Rotas"],
    dependencies=[Depends(require_admin_with_csrf)],
)


def _edit_route_url(route_id: int) -> str:
    return f"/admin/routes/{route_id}/edit"


def _route_and_point(db: Session, route_id: int, object_id: int) -> tuple[Route, MupiObject]:
    route = db.get(Route, route_id)

    if route is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")

    # Só pontos que estão (salvos) na rota
    if object_id not in route.point_ids:
        raise HTTPException(status_code=404, detail="Este ponto não está na rota.")

    return route, db.get(MupiObject, object_id)


def _render(
    request: Request,
    route: Route,
    point: MupiObject,
    draft: ContentDraft,
    exists: bool,
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="admin/route_point_content_form.html",
        context={
            "route": route,
            "point": point,
            "content": draft,
            "exists": exists,
            "form_action": f"/admin/routes/{route.id}/points/{point.id}/content",
            "photo_url": storage_service.url(draft.photo_key),
            "point_photo_url": storage_service.url(point.photo_key),
            "audio_url": storage_service.url(draft.audio_key, storage_service.AUDIO_URL_SECONDS),
            "error": error,
        },
        status_code=status_code,
    )


async def _read(request: Request, field: str, reader):
    upload = await uploaded_file(request, field)

    if upload is None:
        return None

    try:
        return reader(upload)
    except HTTPException as exc:
        raise FormError(exc.detail, exc.status_code)


@router.get("")
def edit_content_form(route_id: int, object_id: int, request: Request, db: Session = Depends(get_db)):
    route, point = _route_and_point(db, route_id, object_id)
    content = get_content(db, route_id, object_id)

    draft = draft_from_content(content) if content else draft_from_point(point)

    return _render(request, route, point, draft, exists=content is not None)


@router.post("")
async def save_content(route_id: int, object_id: int, request: Request, db: Session = Depends(get_db)):
    route, point = _route_and_point(db, route_id, object_id)
    content = get_content(db, route_id, object_id)
    draft = read_content_form(await request.form())

    if content is not None:
        draft.photo_key = content.photo_key
        draft.audio_key = content.audio_key
        draft.audio_duration = content.audio_duration

    try:
        data = validate_content(draft)
        photo = await _read(request, "photo", read_image)
        audio = await _read(request, "audio", read_audio)
    except FormError as exc:
        return _render(
            request, route, point, draft, content is not None,
            error=exc.message, status_code=exc.status_code,
        )

    if content is None:
        content = RoutePointContent(route_id=route_id, object_id=object_id)
        db.add(content)
        db.flush()

    old_keys = {content.photo_key, content.audio_key}
    apply_content(content, data)

    prefix = f"routes/{route_id}/points/{object_id}"
    sent: list[str] = []

    try:
        if photo is not None:
            content.photo_key = store_file(db, prefix, "photo", *photo)
            sent.append(content.photo_key)

        if audio is not None:
            audio_data, mime_type, duration = audio
            content.audio_key = store_file(db, prefix, "audio", audio_data, mime_type)
            content.audio_duration = duration
            sent.append(content.audio_key)
    except HTTPException as exc:
        for key in sent:
            storage_service.delete_quietly(key)
        route, point = _route_and_point(db, route_id, object_id)
        return _render(
            request, route, point, draft, get_content(db, route_id, object_id) is not None,
            error=exc.detail, status_code=exc.status_code,
        )

    if photo is None and draft.remove_photo:
        content.photo_key = None

    if audio is None and draft.remove_audio:
        content.audio_key = None
        content.audio_duration = None

    commit_or_delete_files(db, sent)

    for key in old_keys - {content.photo_key, content.audio_key, None}:
        storage_service.delete_quietly(key)

    return RedirectResponse(
        with_message(_edit_route_url(route_id), "route-point-content-saved"), status_code=303
    )


@router.post("/delete")
def delete_content(route_id: int, object_id: int, db: Session = Depends(get_db)):
    _route_and_point(db, route_id, object_id)
    content = get_content(db, route_id, object_id)

    if content is not None:
        keys = content.file_keys
        db.delete(content)
        db.commit()

        for key in keys:
            storage_service.delete_quietly(key)

    return RedirectResponse(
        with_message(_edit_route_url(route_id), "route-point-content-deleted"), status_code=303
    )
