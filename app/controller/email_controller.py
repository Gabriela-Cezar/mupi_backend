from fastapi import APIRouter, Depends, Form, Request
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.admin_auth import require_admin_with_csrf
from app.core.templates import templates
from app.service.email_service import send_email

# Só administradores logados podem enviar e-mails de teste (FAL-05)
router = APIRouter(
    prefix="/admin/email-test",
    tags=["Administração"],
    dependencies=[Depends(require_admin_with_csrf)]
)

_email_adapter = TypeAdapter(EmailStr)

TEST_SUBJECT = "Teste de e-mail - MUPI"
TEST_HTML = "<h1>MUPI</h1><p>Este é um e-mail de teste do painel administrativo.</p>"


def _page(
    request: Request,
    recipient: str,
    success: str | None = None,
    error: str | None = None,
    status_code: int = 200
):
    return templates.TemplateResponse(
        request=request,
        name="admin/email_test.html",
        context={"recipient": recipient, "success": success, "error": error},
        status_code=status_code
    )


@router.get("")
def email_test_form(request: Request):
    # Sugere o e-mail do próprio administrador
    return _page(request, recipient=request.state.admin.email)


@router.post("")
def send_test_email(
    request: Request,
    recipient: str = Form("")
):
    recipient = recipient.strip()

    try:
        recipient = _email_adapter.validate_python(recipient)
    except ValidationError:
        return _page(
            request,
            recipient=recipient,
            error="Informe um e-mail válido.",
            status_code=400
        )

    ok = send_email(
        recipient=recipient,
        subject=TEST_SUBJECT,
        html_content=TEST_HTML,
    )

    if not ok:
        return _page(
            request,
            recipient=recipient,
            error=(
                "Falha ao enviar o e-mail. Confira a RESEND_API_KEY, o "
                "EMAIL_FROM e se o domínio está verificado no Resend."
            ),
            status_code=502
        )

    return _page(
        request,
        recipient=recipient,
        success=f"E-mail de teste enviado para {recipient}."
    )
