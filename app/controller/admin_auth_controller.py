from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.admin_auth import (
    SESSION_COOKIE,
    admin_from_session,
    clear_failed_logins,
    login_blocked,
    register_failed_login,
    require_admin_with_csrf,
    safe_next_url,
)
from app.core.config import ADMIN_COOKIE_SECURE
from app.core.security import ADMIN_SESSION_HOURS, create_admin_session_token
from app.core.templates import templates
from app.database.database import get_db
from app.service.admin_service import authenticate_admin
from app.service.auth_service import normalize_email

router = APIRouter(
    prefix="/admin",
    tags=["Administração - Login"]
)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def _login_page(
    request: Request,
    next_url: str,
    email: str = "",
    error: str | None = None,
    status_code: int = 200
):
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"next": next_url, "email": email, "error": error},
        status_code=status_code
    )


@router.get("/login")
def login_form(
    request: Request,
    next: str | None = None,
    db: Session = Depends(get_db)
):
    next_url = safe_next_url(next)

    # Já está logado: não precisa ver a tela de login
    if admin_from_session(db, request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse(next_url, status_code=303)

    return _login_page(request, next_url)


@router.post("/login")
def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    next: str = Form(""),
    db: Session = Depends(get_db)
):
    next_url = safe_next_url(next)
    email = normalize_email(email)
    ip = _client_ip(request)

    if login_blocked(ip, email):
        return _login_page(
            request,
            next_url,
            email=email,
            error="Muitas tentativas. Aguarde 15 minutos e tente novamente.",
            status_code=429
        )

    admin = authenticate_admin(db, email, password) if email and password else None

    if admin is None:
        register_failed_login(ip, email)

        return _login_page(
            request,
            next_url,
            email=email,
            error="E-mail ou senha inválidos.",
            status_code=401
        )

    clear_failed_logins(ip, email)

    response = RedirectResponse(next_url, status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_admin_session_token(admin.id, admin.password_hash),
        max_age=ADMIN_SESSION_HOURS * 3600,
        path="/admin",
        httponly=True,
        secure=ADMIN_COOKIE_SECURE,
        samesite="lax",
    )

    return response


@router.post("/logout", dependencies=[Depends(require_admin_with_csrf)])
def logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/admin",
        httponly=True,
        secure=ADMIN_COOKIE_SECURE,
        samesite="lax",
    )

    return response
