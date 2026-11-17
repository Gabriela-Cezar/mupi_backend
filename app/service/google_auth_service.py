"""Validação do id_token do Google (USR-04), com a biblioteca oficial.

Confere a assinatura (chaves públicas do Google), a validade, o emissor e se
o token foi emitido para um dos Client IDs do projeto (GOOGLE_CLIENT_IDS).
Só aceita e-mail verificado pelo Google.
"""
from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core import config

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleLoginDisabled(Exception):
    """GOOGLE_CLIENT_IDS não configurado."""


class GoogleTokenError(Exception):
    """Token inválido, vencido, de outro app ou com e-mail não verificado."""


@dataclass
class GoogleIdentity:
    sub: str
    email: str
    issued_at: int


# Reaproveita a conexão e o cache das chaves públicas do Google
_transport = google_requests.Request()


def _decode(token: str) -> dict:
    """Valida assinatura e validade. Separada para os testes simularem."""
    return google_id_token.verify_oauth2_token(token, _transport, audience=None)


def verify_google_token(token: str) -> GoogleIdentity:
    client_ids = config.GOOGLE_CLIENT_IDS

    if not client_ids:
        raise GoogleLoginDisabled("Login com Google não configurado (GOOGLE_CLIENT_IDS).")

    try:
        claims = _decode(token)
    except Exception as exc:  # a biblioteca levanta tipos variados
        raise GoogleTokenError("Token do Google inválido ou vencido.") from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenError("Token não foi emitido pelo Google.")

    # Emitido para o nosso app (Android, iOS ou web), e não para outro
    if claims.get("aud") not in client_ids:
        raise GoogleTokenError("Token do Google emitido para outro aplicativo.")

    if claims.get("email_verified") is not True or not claims.get("email"):
        raise GoogleTokenError("O e-mail desta conta Google não foi verificado.")

    sub = claims.get("sub")
    if not sub:
        raise GoogleTokenError("Token do Google sem identificação da conta.")

    return GoogleIdentity(
        sub=str(sub),
        email=str(claims["email"]),
        issued_at=int(claims.get("iat", 0)),
    )
