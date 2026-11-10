"""Autenticação do painel administrativo (ADM-01 / FAL-04)."""
import hmac
import time
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import (
    csrf_token_for,
    decode_admin_session_token,
    fingerprint_matches,
)
from app.database.database import get_db
from app.model.admin import Admin

SESSION_COOKIE = "mupi_admin_session"
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

DEFAULT_ADMIN_PAGE = "/admin/mupi-objects"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# ---------- Sessão ----------

def admin_from_session(db: Session, token: str | None) -> Admin | None:
    if not token:
        return None

    payload = decode_admin_session_token(token)

    if payload is None:
        return None

    try:
        admin_id = int(payload["sub"])
    except (KeyError, ValueError):
        return None

    admin = db.get(Admin, admin_id)

    # Trocar a senha ou desativar o admin derruba as sessões abertas
    if (
        admin is None
        or not admin.is_active
        or not fingerprint_matches(payload, admin.password_hash)
    ):
        return None

    return admin


def _wants_html(request: Request) -> bool:
    return (
        request.method == "GET"
        and "text/html" in request.headers.get("accept", "")
    )


def require_admin(
    request: Request,
    db: Session = Depends(get_db)
) -> Admin:
    token = request.cookies.get(SESSION_COOKIE)
    admin = admin_from_session(db, token)

    if admin is None:
        # Navegador abrindo uma página: manda para o login e volta depois
        if _wants_html(request):
            next_url = request.url.path
            if request.url.query:
                next_url += f"?{request.url.query}"

            raise HTTPException(
                status_code=303,
                headers={"Location": f"/admin/login?next={quote(next_url)}"}
            )

        raise HTTPException(
            status_code=401,
            detail="Faça login no painel administrativo."
        )

    request.state.admin = admin
    request.state.csrf_token = csrf_token_for(token)

    return admin


async def require_admin_with_csrf(
    request: Request,
    admin: Admin = Depends(require_admin)
) -> Admin:
    """Exige login e, em envios (POST etc.), o token CSRF da sessão."""
    if request.method in _SAFE_METHODS:
        return admin

    sent = request.headers.get(CSRF_HEADER)

    if not sent:
        form = await request.form()
        sent = form.get(CSRF_FIELD)

    if not isinstance(sent, str) or not hmac.compare_digest(
        sent, request.state.csrf_token
    ):
        raise HTTPException(
            status_code=403,
            detail="Formulário expirado ou inválido. Recarregue a página e tente novamente."
        )

    return admin


# ---------- Redirecionamento seguro após o login ----------

def safe_next_url(next_url: str | None) -> str:
    """Só aceita páginas do próprio painel (evita redirecionar para outro site)."""
    if (
        not next_url
        or not next_url.startswith("/admin")
        or next_url.startswith("//")
        or "\\" in next_url
        or next_url.startswith("/admin/login")
    ):
        return DEFAULT_ADMIN_PAGE

    return next_url


# ---------- Limite de tentativas de login ----------

MAX_FAILED_LOGINS = 5
FAILED_LOGIN_WINDOW_SECONDS = 15 * 60

# Em memória: suficiente para um único processo. Ver INF-08 para a versão final.
_failed_logins: dict[tuple[str, str], list[float]] = {}


def _recent_failures(key: tuple[str, str]) -> list[float]:
    limit = time.monotonic() - FAILED_LOGIN_WINDOW_SECONDS
    attempts = [t for t in _failed_logins.get(key, []) if t > limit]

    if attempts:
        _failed_logins[key] = attempts
    else:
        _failed_logins.pop(key, None)

    return attempts


def login_blocked(ip: str, email: str) -> bool:
    return len(_recent_failures((ip, email))) >= MAX_FAILED_LOGINS


def register_failed_login(ip: str, email: str) -> None:
    _failed_logins.setdefault((ip, email), []).append(time.monotonic())


def clear_failed_logins(ip: str, email: str) -> None:
    _failed_logins.pop((ip, email), None)
