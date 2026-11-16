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


def format_duration(seconds: int | None) -> str:
    """Duração em "m:ss" (ex.: 125 → "2:05"); "—" se não houver."""
    if seconds is None:
        return "—"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}:{rest:02d}"


templates.env.filters["duration"] = format_duration
