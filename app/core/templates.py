from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.core.admin_messages import message_for

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _admin_context(request: Request) -> dict:
    """Disponibiliza o admin logado, o token CSRF e a mensagem de sucesso
    (`?msg=`) em todos os templates."""
    return {
        "current_admin": getattr(request.state, "admin", None),
        "csrf_token": getattr(request.state, "csrf_token", ""),
        "success_message": message_for(request.query_params.get("msg")),
    }


templates = Jinja2Templates(
    directory=TEMPLATES_DIR,
    context_processors=[_admin_context]
)
