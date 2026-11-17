"""Telas de rotas do painel (ADM-07, ADM-08, ADM-09, ADM-12; ROT-01 a ROT-03).

- lista: /admin/routes
- cadastro: /admin/routes/new
- edição: /admin/routes/{id}/edit
- recalcular trajeto: POST /admin/routes/{id}/path
- ativar/desativar: POST /admin/routes/{id}/status
- excluir (com confirmação): /admin/routes/{id}/delete

O trajeto é calculado ao salvar quando os pontos ou a ordem mudam. Se o
cálculo falhar, a rota é salva assim mesmo, desativada e sem trajeto, e a
edição mostra o erro e o botão "Recalcular trajeto".
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import distinct, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.controller.admin_files import (
    commit_or_delete_files,
    read_image,
    store_file,
    uploaded_file,
)
from app.controller.mupi_object_form import FormError
from app.controller.route_form import (
    AGE_RATING_LABELS,
    DIFFICULTY_LABELS,
    RouteDraft,
    activation_problems,
    apply_route,
    draft_from_route,
    read_route_form,
    validate_route,
)
from app.core.admin_auth import require_admin_with_csrf
from app.core.admin_messages import with_message
from app.core.templates import templates
from app.database.database import get_db
from app.model.badge import Badge
from app.model.mupi_object import MupiObject
from app.model.route import Route, RoutePoint
from app.model.theme import Theme
from app.model.user_route_completion import UserRouteCompletion
from app.service import storage_service
from app.service.route_point_content_service import (
    contents_for_route,
    remove_contents_outside,
    route_file_keys,
)
from app.model.user_active_route import CancelReason
from app.service.active_route_service import cancel_progress, users_doing
from app.service.route_path_service import update_route_path

LIST_URL = "/admin/routes"

router = APIRouter(
    prefix=LIST_URL,
    tags=["Administração - Rotas"],
    dependencies=[Depends(require_admin_with_csrf)]
)


def _redirect(code: str, path: str = LIST_URL) -> RedirectResponse:
    return RedirectResponse(with_message(path, code), status_code=303)


def _route_options():
    return (
        selectinload(Route.points).selectinload(RoutePoint.mupi_object),
        selectinload(Route.themes),
    )


def _get_route(db: Session, route_id: int) -> Route:
    route = (
        db.query(Route)
        .options(*_route_options())
        .filter(Route.id == route_id)
        .first()
    )

    if route is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")

    return route


# ---------- Lista ----------

def _render_list(request: Request, db: Session, error: str | None = None, status_code: int = 200):
    routes = (
        db.query(Route)
        .options(*_route_options())
        .order_by(Route.name)
        .all()
    )

    rows = [
        {
            "route": route,
            "difficulty": DIFFICULTY_LABELS[route.difficulty],
            "inactive_points": [
                rp.mupi_object.name for rp in route.points if not rp.mupi_object.active
            ],
        }
        for route in routes
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin/route_list.html",
        context={"rows": rows, "error": error},
        status_code=status_code,
    )


@router.get("")
def list_routes(request: Request, db: Session = Depends(get_db)):
    return _render_list(request, db)


# ---------- Formulário (cadastro e edição) ----------

def _render_form(
    request: Request,
    db: Session,
    draft: RouteDraft,
    route: Route | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    points = db.query(MupiObject).order_by(MupiObject.name).all()
    by_id = {p.id: p for p in points}

    # Pontos escolhidos, na ordem do formulário (para mostrar a lista)
    selected = [
        by_id[int(i)] for i in draft.point_ids
        if i.isdigit() and int(i) in by_id
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin/route_form.html",
        context={
            "route": draft,
            "saved": route,
            "editing": route is not None,
            "form_action": f"{LIST_URL}/{route.id}/edit" if route else LIST_URL,
            "cover_url": storage_service.url(draft.cover_key),
            "points": points,
            "selected_points": selected,
            "themes": db.query(Theme).order_by(Theme.name).all(),
            "difficulties": [(d.value, label) for d, label in DIFFICULTY_LABELS.items()],
            "age_ratings": [(a.value, label) for a, label in AGE_RATING_LABELS.items()],
            "problems": activation_problems(route) if route is not None else [],
            # Pontos salvos na rota (podem ter conteúdo próprio nela)
            "saved_point_ids": set(route.point_ids) if route is not None else set(),
            "custom_point_ids": set(contents_for_route(db, route.id)) if route is not None else set(),
            # Aviso: mudar os pontos ou desativar encerra o progresso (ADM-07)
            "users_doing": users_doing(db, route.id) if route is not None else 0,
            "error": error,
        },
        status_code=status_code,
    )


async def _read_cover(request: Request) -> tuple[bytes, str] | None:
    cover = await uploaded_file(request, "cover")

    if cover is None:
        return None

    try:
        return read_image(cover)
    except HTTPException as exc:
        raise FormError(exc.detail, exc.status_code)


def _save(
    db: Session,
    route: Route,
    draft: RouteDraft,
    data,
    cover: tuple[bytes, str] | None,
) -> tuple[list[str], str | None, list[str]]:
    """Grava a rota, calcula o trajeto se preciso e confere a ativação.

    Devolve (arquivos enviados, código da mensagem, arquivos a apagar depois
    de gravar: os do conteúdo dos pontos que saíram). Erros de envio da capa
    sobem como HTTPException.

    Mudar os pontos/a ordem ou desativar encerra o progresso de quem está
    fazendo a rota (ROT-10). Nome, descrição e capa não afetam o progresso.
    """
    was_active = route.active
    points_changed = apply_route(db, route, data)
    db.flush()

    # Ponto que saiu da rota: o conteúdo dele nesta rota vai junto
    removed = remove_contents_outside(db, route) if points_changed else []

    sent: list[str] = []

    if cover is not None:
        route.cover_key = store_file(db, f"routes/{route.id}", "cover", *cover)
        sent.append(route.cover_key)
    elif draft.remove_cover:
        route.cover_key = None

    path_ok = True
    if points_changed or not route.has_path:
        path_ok = update_route_path(route)

    # Ativar só se nada faltar; senão a rota fica desativada (ROT-01, ROT-03)
    problems = activation_problems(route)
    route.active = data.active and not problems

    if route.id is not None and points_changed:
        cancel_progress(db, route.id, CancelReason.ROUTE_UPDATED)
    elif was_active and not route.active:
        cancel_progress(db, route.id, CancelReason.ROUTE_DEACTIVATED)

    if not path_ok:
        return sent, "route-saved-path-error", removed

    if data.active and problems:
        return sent, "route-saved-inactive", removed

    return sent, None, removed


@router.get("/new")
def new_route_form(request: Request, db: Session = Depends(get_db)):
    return _render_form(request, db, RouteDraft())


@router.post("")
async def create_route(request: Request, db: Session = Depends(get_db)):
    draft = read_route_form(await request.form())

    try:
        data = validate_route(db, draft)
        cover = await _read_cover(request)
    except FormError as exc:
        return _render_form(request, db, draft, error=exc.message, status_code=exc.status_code)

    route = Route()
    db.add(route)

    try:
        sent, warning, _ = _save(db, route, draft, data, cover)
    except HTTPException as exc:
        return _render_form(request, db, draft, error=exc.detail, status_code=exc.status_code)

    try:
        commit_or_delete_files(db, sent)
    except IntegrityError:
        return _render_form(
            request, db, draft, error="Já existe uma rota com esse nome.", status_code=400
        )

    if warning:
        return _redirect(warning, f"{LIST_URL}/{route.id}/edit")

    return _redirect("route-created")


@router.get("/{route_id}/edit")
def edit_route_form(route_id: int, request: Request, db: Session = Depends(get_db)):
    route = _get_route(db, route_id)

    return _render_form(request, db, draft_from_route(route), route=route)


@router.post("/{route_id}/edit")
async def update_route(route_id: int, request: Request, db: Session = Depends(get_db)):
    route = _get_route(db, route_id)
    draft = read_route_form(await request.form())
    draft.cover_key = route.cover_key

    try:
        data = validate_route(db, draft, route=route)
        cover = await _read_cover(request)
    except FormError as exc:
        return _render_form(
            request, db, draft, route=route, error=exc.message, status_code=exc.status_code
        )

    old_cover = route.cover_key

    try:
        sent, warning, removed = _save(db, route, draft, data, cover)
    except HTTPException as exc:
        route = _get_route(db, route_id)
        return _render_form(
            request, db, draft, route=route, error=exc.detail, status_code=exc.status_code
        )

    try:
        commit_or_delete_files(db, sent)
    except IntegrityError:
        route = _get_route(db, route_id)
        return _render_form(
            request, db, draft, route=route,
            error="Já existe uma rota com esse nome.", status_code=400,
        )

    if old_cover and old_cover != route.cover_key:
        storage_service.delete_quietly(old_cover)

    for key in removed:
        storage_service.delete_quietly(key)

    if warning:
        return _redirect(warning, f"{LIST_URL}/{route.id}/edit")

    return _redirect("route-updated")


# ---------- Recalcular trajeto (ROT-03) ----------

@router.post("/{route_id}/path")
def recalculate_path(route_id: int, db: Session = Depends(get_db)):
    route = _get_route(db, route_id)

    was_active = route.active
    ok = update_route_path(route)

    # Sem trajeto, a rota é desativada: encerra o progresso (ROT-10)
    if was_active and not route.active:
        cancel_progress(db, route.id, CancelReason.ROUTE_DEACTIVATED)

    db.commit()

    return _redirect(
        "route-path-updated" if ok else "route-path-error",
        f"{LIST_URL}/{route.id}/edit",
    )


# ---------- Ativar e desativar (ADM-08) ----------

@router.post("/{route_id}/status")
async def set_route_status(route_id: int, request: Request, db: Session = Depends(get_db)):
    route = _get_route(db, route_id)
    form = await request.form()
    activate = str(form.get("active", "")).lower() == "true"

    if activate:
        problems = activation_problems(route)

        if problems:
            return _render_list(
                request, db,
                error=f"A rota {route.name} não pode ser ativada: " + " ".join(problems),
                status_code=400,
            )

    route.active = activate

    # Desativar encerra o progresso de quem está fazendo a rota (ROT-10)
    if not activate:
        cancel_progress(db, route.id, CancelReason.ROUTE_DEACTIVATED)

    db.commit()

    return _redirect("route-activated" if activate else "route-deactivated")


# ---------- Excluir (ADM-09) ----------

def delete_blockers(db: Session, route: Route) -> list[str]:
    """Rota concluída por alguém ou com insígnia de conclusão não pode ser
    excluída: a conclusão e a insígnia ficam com o usuário (ADM-09). O
    painel oferece desativar. Vazio = pode excluir."""
    reasons = []

    users = (
        db.query(func.count(distinct(UserRouteCompletion.user_id)))
        .filter(UserRouteCompletion.route_id == route.id)
        .scalar()
    ) or 0

    if users == 1:
        reasons.append("1 usuário já concluiu esta rota.")
    elif users:
        reasons.append(f"{users} usuários já concluíram esta rota.")

    badge = db.query(Badge.name).filter(Badge.route_id == route.id).first()

    if badge is not None:
        reasons.append(f"Tem a insígnia de conclusão: {badge[0]}.")

    return reasons


def _render_delete(request: Request, route: Route, blockers: list[str], status_code: int = 200):
    consequences = ["A ordem dos pontos e o trajeto são apagados. Os pontos continuam cadastrados."]

    if route.cover_key:
        consequences.append("A imagem de capa é apagada do armazenamento.")

    return templates.TemplateResponse(
        request=request,
        name="admin/confirm_delete.html",
        context={
            "title": "Excluir rota",
            "item_name": route.name,
            "blockers": blockers,
            "consequences": consequences,
            "delete_action": f"{LIST_URL}/{route.id}/delete",
            "cancel_url": LIST_URL,
            "deactivate_action": f"{LIST_URL}/{route.id}/status" if route.active else None,
        },
        status_code=status_code,
    )


@router.get("/{route_id}/delete")
def confirm_delete_route(route_id: int, request: Request, db: Session = Depends(get_db)):
    route = _get_route(db, route_id)

    return _render_delete(request, route, delete_blockers(db, route))


@router.post("/{route_id}/delete")
def delete_route(route_id: int, request: Request, db: Session = Depends(get_db)):
    route = _get_route(db, route_id)
    blockers = delete_blockers(db, route)

    if blockers:
        return _render_delete(request, route, blockers, status_code=409)

    file_keys = [route.cover_key, *route_file_keys(db, route.id)]
    db.delete(route)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        route = _get_route(db, route_id)
        return _render_delete(request, route, ["A rota tem histórico de uso."], status_code=409)

    for key in file_keys:
        storage_service.delete_quietly(key)

    return _redirect("route-deleted")
