from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _admin_context(request: Request) -> dict:
    """Disponibiliza o admin logado e o token CSRF em todos os templates."""
    return {
        "current_admin": getattr(request.state, "admin", None),
        "csrf_token": getattr(request.state, "csrf_token", ""),
    }


templates = Jinja2Templates(
    directory=TEMPLATES_DIR,
    context_processors=[_admin_context]
)
