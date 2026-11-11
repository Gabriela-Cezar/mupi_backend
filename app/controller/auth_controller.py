from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.rate_limit import RateLimiter, format_wait, too_many_requests
from app.core.security import (
    create_access_token,
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
    RESEND_COOLDOWN_SECONDS,
    gerar_codigo,
    gerar_codigo_recuperacao,
    renovar_codigo,
    verificar_codigo,
    verificar_codigo_recuperacao,
)
from app.service.email_service import send_email


router = APIRouter(
    prefix="/auth",
    tags=["Autenticação"]
)


# ---------- Limite de envio de e-mails (FAL-07) ----------

# Por e-mail: um código a cada 60 s (o reenvio já tem o próprio intervalo)
register_email_limiter = RateLimiter(1, RESEND_COOLDOWN_SECONDS)
recovery_email_limiter = RateLimiter(1, RESEND_COOLDOWN_SECONDS)

# Por IP: soma cadastro, recuperação e reenvio, para o servidor não ser usado
# para mandar e-mails a muitos endereços
EMAIL_REQUESTS_PER_IP = 10
EMAIL_REQUESTS_WINDOW_SECONDS = 15 * 60
email_ip_limiter = RateLimiter(EMAIL_REQUESTS_PER_IP, EMAIL_REQUESTS_WINDOW_SECONDS)


def _client_ip(request: Request) -> str:
    # Atrás de um proxy (Nginx na AWS), o uvicorn precisa de --proxy-headers
    # para este ser o IP real do usuário (INF-05)
    return request.client.host if request.client else "desconhecido"


def _limit_email_requests_by_ip(request: Request) -> None:
    wait = email_ip_limiter.hit(_client_ip(request))

    if wait:
        raise too_many_requests(
            wait,
            "Muitas solicitações de código a partir desta rede. "
            f"Aguarde {format_wait(wait)} e tente novamente."
        )


# ---------- Limite de tentativas de login (FAL-08) ----------

LOGIN_WINDOW_SECONDS = 15 * 60

# Mesmo e-mail a partir da mesma rede: alguém tentando adivinhar uma senha.
# Não há limite por e-mail de qualquer rede: senão, errar de propósito
# trancaria a conta de outra pessoa.
LOGIN_FAILURES_PER_IP_AND_EMAIL = 5
login_ip_email_limiter = RateLimiter(LOGIN_FAILURES_PER_IP_AND_EMAIL, LOGIN_WINDOW_SECONDS)

# Mesma rede, qualquer e-mail: alguém testando senhas vazadas em muitas contas
LOGIN_FAILURES_PER_IP = 20
login_ip_limiter = RateLimiter(LOGIN_FAILURES_PER_IP, LOGIN_WINDOW_SECONDS)


def _code_cooldown(wait: int) -> HTTPException:
    return too_many_requests(
        wait,
        f"Aguarde {format_wait(wait)} para pedir outro código."
    )


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


@router.post("/register")
def register(
    data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    _limit_email_requests_by_ip(request)

    email = normalize_email(data.email)

    if get_user_by_email(db, email):
        raise HTTPException(
            status_code=400,
            detail="E-mail já cadastrado"
        )

    wait = register_email_limiter.retry_after(email)

    if wait:
        raise _code_cooldown(wait)

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
        # Não conta o intervalo: o usuário pode tentar de novo na hora
        raise HTTPException(
            status_code=503,
            detail="Não foi possível enviar o e-mail. Tente novamente."
        )

    register_email_limiter.record(email)

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

@router.post("/login")
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    ip = _client_ip(request)
    ip_and_email = (ip, normalize_email(data.email))

    # Bloqueado responde 429 mesmo com a senha certa: senão o atacante
    # saberia que acertou
    wait = max(
        login_ip_email_limiter.retry_after(ip_and_email),
        login_ip_limiter.retry_after(ip),
    )

    if wait:
        raise too_many_requests(
            wait,
            "Muitas tentativas de login. "
            f"Aguarde {format_wait(wait)} e tente novamente."
        )

    user = authenticate_user(
        db=db,
        email=data.email,
        password=data.password
    )

    if user is None:
        login_ip_email_limiter.record(ip_and_email)
        login_ip_limiter.record(ip)

        raise HTTPException(
            status_code=401,
            detail="E-mail ou senha inválidos"
        )

    # Login certo zera as falhas deste e-mail nesta rede
    login_ip_email_limiter.forget(ip_and_email)

    return {
        "message": "Login realizado com sucesso",
        "access_token": create_access_token(user.id, user.password_hash),
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email
    }


@router.post("/recovery-password")
def recovery_password(
    data: RecoveryPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    _limit_email_requests_by_ip(request)

    # O intervalo vale para qualquer e-mail, com conta ou não: se valesse só
    # para quem tem conta, o 429 revelaria quem está cadastrado
    wait = recovery_email_limiter.hit(normalize_email(data.email))

    if wait:
        raise _code_cooldown(wait)

    user = get_user_by_email(db, data.email)

    if user is not None:
        codigo = gerar_codigo_recuperacao(user.email)

        background_tasks.add_task(
            send_email,
            recipient=user.email,
            subject="Código para recuperação de senha - MUPI",
            html_content=recovery_email_html(codigo),
        )

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
    request: Request,
    background_tasks: BackgroundTasks
):
    _limit_email_requests_by_ip(request)

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