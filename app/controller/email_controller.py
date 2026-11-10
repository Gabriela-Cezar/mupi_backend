from fastapi import APIRouter, HTTPException
from pydantic import EmailStr

from app.service.email_service import send_email


router = APIRouter(prefix="/email", tags=["Email"])


@router.post("/test")
def test_email(recipient: EmailStr):
    ok = send_email(
        recipient=recipient,
        subject="Teste de e-mail - MUPI",
        html_content="<h1>MUPI</h1><p>Este é um e-mail de teste.</p>",
    )

    if not ok:
        raise HTTPException(status_code=502, detail="Falha ao enviar e-mail.")

    return {"message": "E-mail enviado com sucesso"}