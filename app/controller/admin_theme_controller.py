"""Telas de temas do painel (ADM-05, ADM-09, ADM-12).

- lista + cadastro: /admin/themes
- edição: /admin/themes/{id}/edit
- excluir (com confirmação): /admin/themes/{id}/delete
"""
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.admin_auth import require_admin_with_csrf
from app.core.admin_messages import with_message
from app.core.templates import templates
from app.database.database import get_db
from app.model.badge import Badge
from app.model.mupi_object_theme import MupiObjectTheme
from app.model.route import RouteTheme
from app.model.theme import Theme

LIST_URL = "/admin/themes"
MAX_NAME = 100
MAX_DESCRIPTION = 2_000

# Todas as rotas exigem login (e token CSRF nos envios)
router = APIRouter(
    prefix=LIST_URL,
    tags=["Administração - Temas"],
    dependencies=[Depends(require_admin_with_csrf)]
)


class ThemeFormError(Exception):
    pass


def _redirect(code: str) -> RedirectResponse:
    return RedirectResponse(with_message(LIST_URL, code), status_code=303)


def _get_theme(db: Session, theme_id: int) -> Theme:
    theme = db.get(Theme, theme_id)

    if theme is None:
        raise HTTPException(status_code=404, detail="Tema não encontrado.")

    return theme


def _counts(db: Session, column) -> dict[int, int]:
    return dict(
        db.query(column, func.count())
        .filter(column.isnot(None))
        .group_by(column)
        .all()
    )


async def _read_form(request: Request) -> SimpleNamespace:
    form = await request.form()

    def text(name):
        value = form.get(name)
        return value if isinstance(value, str) else ""

    return SimpleNamespace(name=text("name"), description=text("description"))


def _validate(db: Session, draft: SimpleNamespace, theme_id: int | None = None):
    name = draft.name.strip()
    description = draft.description.replace("\r\n", "\n").strip() or None

    if not name:
        raise ThemeFormError("Informe o nome do tema.")

    if len(name) > MAX_NAME:
        raise ThemeFormError(f"Nome: máximo de {MAX_NAME} caracteres.")

    if description and len(description) > MAX_DESCRIPTION:
        raise ThemeFormError(f"Descrição: máximo de {MAX_DESCRIPTION} caracteres.")

    # "Arte Deco" e "arte deco" são o mesmo tema
    duplicate = db.query(Theme.id).filter(func.lower(Theme.name) == name.lower())

    if theme_id is not None:
        duplicate = duplicate.filter(Theme.id != theme_id)

    if duplicate.first():
        raise ThemeFormError("Já existe um tema com esse nome.")

    return name, description


# ---------- Lista e cadastro ----------

def _render_list(
    request: Request,
    db: Session,
    draft: SimpleNamespace | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="admin/theme_list.html",
        context={
            "themes": db.query(Theme).order_by(Theme.name).all(),
            "points": _counts(db, MupiObjectTheme.theme_id),
            "badges": _counts(db, Badge.theme_id),
            "draft": draft or SimpleNamespace(name="", description=""),
            "error": error,
        },
        status_code=status_code,
    )


@router.get("")
def list_themes(request: Request, db: Session = Depends(get_db)):
    return _render_list(request, db)


@router.get("/new")
def old_theme_form():
    """Endereço antigo da tela de temas."""
    return RedirectResponse(LIST_URL, status_code=303)


@router.post("")
async def create_theme(request: Request, db: Session = Depends(get_db)):
    draft = await _read_form(request)

    try:
        name, description = _validate(db, draft)
    except ThemeFormError as exc:
        return _render_list(request, db, draft, error=str(exc), status_code=400)

    db.add(Theme(name=name, description=description))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_list(
            request, db, draft, error="Já existe um tema com esse nome.", status_code=400
        )

    return _redirect("theme-created")


# ---------- Edição ----------

def _render_edit(
    request: Request,
    theme_id: int,
    draft: SimpleNamespace,
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="admin/theme_form.html",
        context={"theme_id": theme_id, "draft": draft, "error": error},
        status_code=status_code,
    )


@router.get("/{theme_id}/edit")
def edit_theme_form(theme_id: int, request: Request, db: Session = Depends(get_db)):
    theme = _get_theme(db, theme_id)
    draft = SimpleNamespace(name=theme.name, description=theme.description or "")

    return _render_edit(request, theme.id, draft)


@router.post("/{theme_id}/edit")
async def update_theme(theme_id: int, request: Request, db: Session = Depends(get_db)):
    theme = _get_theme(db, theme_id)
    draft = await _read_form(request)

    try:
        theme.name, theme.description = _validate(db, draft, theme_id=theme.id)
        db.commit()
    except ThemeFormError as exc:
        return _render_edit(request, theme_id, draft, error=str(exc), status_code=400)
    except IntegrityError:
        db.rollback()
        return _render_edit(
            request, theme_id, draft,
            error="Já existe um tema com esse nome.", status_code=400,
        )

    return _redirect("theme-updated")


# ---------- Excluir (ADM-09) ----------

def delete_blockers(db: Session, theme: Theme) -> list[str]:
    """Tema usado por insígnia não pode ser excluído. Vazio = pode excluir."""
    badge_names = [
        name for (name,) in db.query(Badge.name)
        .filter(Badge.theme_id == theme.id)
        .order_by(Badge.name)
    ]

    if badge_names:
        return ["É usado pela insígnia: " + ", ".join(badge_names) + "."]

    return []


def _render_delete(
    request: Request,
    db: Session,
    theme: Theme,
    blockers: list[str],
    status_code: int = 200,
):
    points = (
        db.query(MupiObjectTheme)
        .filter(MupiObjectTheme.theme_id == theme.id)
        .count()
    )

    routes = (
        db.query(RouteTheme)
        .filter(RouteTheme.theme_id == theme.id)
        .count()
    )

    consequences = []

    if points:
        consequences.append(
            f"{points} ponto(s) deixam de ter este tema. Os pontos continuam cadastrados."
        )

    if routes:
        consequences.append(
            f"{routes} rota(s) deixam de ter este tema. As rotas continuam cadastradas."
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/confirm_delete.html",
        context={
            "title": "Excluir tema",
            "item_name": theme.name,
            "blockers": blockers,
            "consequences": consequences,
            "delete_action": f"{LIST_URL}/{theme.id}/delete",
            "cancel_url": LIST_URL,
            "deactivate_action": None,
        },
        status_code=status_code,
    )


@router.get("/{theme_id}/delete")
def confirm_delete_theme(theme_id: int, request: Request, db: Session = Depends(get_db)):
    theme = _get_theme(db, theme_id)

    return _render_delete(request, db, theme, delete_blockers(db, theme))


@router.post("/{theme_id}/delete")
def delete_theme(theme_id: int, request: Request, db: Session = Depends(get_db)):
    theme = _get_theme(db, theme_id)
    blockers = delete_blockers(db, theme)

    if blockers:
        return _render_delete(request, db, theme, blockers, status_code=409)

    # Remove só as ligações com os pontos e as rotas; eles continuam (PT-03)
    db.query(MupiObjectTheme).filter(MupiObjectTheme.theme_id == theme.id).delete()
    db.query(RouteTheme).filter(RouteTheme.theme_id == theme.id).delete()
    db.delete(theme)

    try:
        db.commit()
    except IntegrityError:
        # Uma insígnia passou a usar o tema entre a conferência e a exclusão
        db.rollback()
        theme = _get_theme(db, theme_id)
        return _render_delete(
            request, db, theme,
            delete_blockers(db, theme) or ["O tema está em uso."],
            status_code=409,
        )

    return _redirect("theme-deleted")
