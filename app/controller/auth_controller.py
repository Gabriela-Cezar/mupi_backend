from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_reset_token,
    decode_reset_token,
    reset_token_matches,
)

from app.core.security import (
    create_reset_token,
    decode_reset_token,
    reset_token_matches,
)
from app.database.database import get_db
from app.service.auth_service import (
    authenticate_user,
    create_user,
    gerar_password_hash,
    get_user_by_email,
    normalize_email,
)
from app.service.auth_user_email_service import (
    gerar_codigo,
    gerar_codigo_recuperacao,
    verificar_codigo,
    verificar_codigo_recuperacao,
)
from app.service.email_service import send_email


router = APIRouter(
    prefix="/auth",
    tags=["Autenticação"]
)


# ---------- Schemas ----------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    codigo: str = Field(pattern=r"^\d{6}$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class RecoveryPasswordRequest(BaseModel):
    email: EmailStr


class VerifyRecoveryCodeRequest(BaseModel):
    email: EmailStr
    codigo: str = Field(pattern=r"^\d{6}$")


class ResetPasswordRequest(BaseModel):
    reset_token: str
    password: str = Field(min_length=8, max_length=128)


# ---------- Templates de e-mail ----------

def _codigo_email_html(titulo: str, intro: str, codigo: str, aviso: str) -> str:
    return f"""
    <html>
        <body>
            <h2>{titulo}</h2>

            <p>Olá!</p>

            <p>{intro}</p>

            <h1>{codigo}</h1>

            <p>
                Este código é válido por <strong>10 minutos</strong>.
            </p>

            <p>{aviso}</p>

            <p>
                Atenciosamente,<br>
                Equipe MUPI
            </p>
        </body>
    </html>
    """


def verification_email_html(codigo: str) -> str:
    return _codigo_email_html(
        titulo="Verificação de e-mail",
        intro="Seu código de verificação para criar sua conta no MUPI é:",
        codigo=codigo,
        aviso="Se você não solicitou este cadastro, ignore este e-mail.",
    )


def recovery_email_html(codigo: str) -> str:
    return _codigo_email_html(
        titulo="Recuperação de senha",
        intro="Seu código para recuperar a senha da sua conta MUPI é:",
        codigo=codigo,
        aviso="Se você não solicitou a recuperação de senha, ignore este e-mail.",
    )


# ---------- Cadastro ----------

@router.post("/register")
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db)
):
    email = normalize_email(data.email)

    if get_user_by_email(db, email):
        raise HTTPException(
            status_code=400,
            detail="E-mail já cadastrado"
        )

    hashed_password = gerar_password_hash(data.password)

    codigo = gerar_codigo(
        email=email,
        hashed_password=hashed_password
    )

    enviado = send_email(
        recipient=email,
        subject="Código de verificação - MUPI",
        html_content=verification_email_html(codigo)
    )

    if not enviado:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível enviar o e-mail. Tente novamente."
        )

    return {
        "message": "Código de verificação enviado para o e-mail.",
        "email": email
    }


@router.post("/verify-email")
def verify_email(
    data: VerifyEmailRequest,
    db: Session = Depends(get_db)
):
    email = normalize_email(data.email)

    valido, mensagem, hashed_password = verificar_codigo(
        email=email,
        codigo_digitado=data.codigo
    )

    if not valido:
        raise HTTPException(
            status_code=400,
            detail=mensagem
        )

    user = create_user(
        db=db,
        email=email,
        hashed_password=hashed_password
    )

    if user is None:
        raise HTTPException(
            status_code=400,
            detail="E-mail já cadastrado"
        )

    return {
        "message": "E-mail verificado e usuário criado com sucesso.",
        "user_id": user.id,
        "email": user.email
    }


# ---------- Login ----------

@router.post("/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = authenticate_user(
        db=db,
        email=data.email,
        password=data.password
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="E-mail ou senha inválidos"
        )

    return {
        "message": "Login realizado com sucesso",
        "access_token": create_access_token(user.id, user.password_hash),
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email
    }


# ---------- Recuperação de senha ----------

@router.post("/recovery-password")
def recovery_password(
    data: RecoveryPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    user = get_user_by_email(db, data.email)

    if user is not None:
        codigo = gerar_codigo_recuperacao(user.email)

        background_tasks.add_task(
            send_email,
            recipient=user.email,
            subject="Código para recuperação de senha - MUPI",
            html_content=recovery_email_html(codigo),
        )

    # Mesma resposta exista o e-mail ou não, para não revelar quem tem conta
    return {
        "message": "Se o e-mail estiver cadastrado, você receberá um código."
    }


@router.post("/verify-recovery-code")
def verify_recovery_code(
    data: VerifyRecoveryCodeRequest,
    db: Session = Depends(get_db)
):
    email = normalize_email(data.email)

    valido, mensagem = verificar_codigo_recuperacao(
        email=email,
        codigo_digitado=data.codigo
    )

    user = get_user_by_email(db, email)

    if not valido or user is None:
        raise HTTPException(
            status_code=400,
            detail=mensagem if not valido else "Código de recuperação inválido."
        )

    return {
        "message": mensagem,
        "reset_token": create_reset_token(user.email, user.password_hash)
    }


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    invalid = HTTPException(
        status_code=400,
        detail="Token de recuperação inválido ou expirado."
    )

    payload = decode_reset_token(data.reset_token)

    if payload is None:
        raise invalid

    user = get_user_by_email(db, payload["sub"])

    if user is None or not reset_token_matches(payload, user.password_hash):
        raise invalid

    user.password_hash = gerar_password_hash(data.password)
    db.commit()

    return {"message": "Senha alterada com sucesso."}

class ResendVerificationRequest(BaseModel):
    email: EmailStr


@router.post("/resend-verification")
def resend_verification(
    data: ResendVerificationRequest,
    background_tasks: BackgroundTasks
):
    email = normalize_email(data.email)

    codigo, espera = renovar_codigo(email)

    if espera > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Aguarde {espera} segundos para reenviar o código."
        )

    if codigo is None:
        raise HTTPException(
            status_code=404,
            detail="Nenhum cadastro pendente para este e-mail. "
                   "Volte e refaça o cadastro."
        )

    background_tasks.add_task(
        send_email,
        recipient=email,
        subject="Código de verificação - MUPI",
        html_content=verification_email_html(codigo),
    )

    return {"message": "Novo código enviado."}