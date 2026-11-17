"""Google simulado para os testes de login (nada sai para a rede).

O teste diz o que cada id_token "contém"; a validação de assinatura e
validade da biblioteca oficial é substituída só aqui.
"""
import time

import pytest

from app.core import config
from app.service import google_auth_service

CLIENT_ID_WEB = "123-web.apps.googleusercontent.com"
CLIENT_ID_ANDROID = "123-android.apps.googleusercontent.com"


class GoogleFalso:
    def __init__(self):
        self.tokens: dict[str, dict] = {}

    def conta(self, token="token-da-ana", sub="google-sub-ana", email="ana@gmail.com", **extras):
        """Registra um id_token válido para esta conta Google."""
        self.tokens[token] = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID_WEB,
            "sub": sub,
            "email": email,
            "email_verified": True,
            "iat": int(time.time()),
            **extras,
        }
        return token

    def decode(self, token):
        if token not in self.tokens:
            raise ValueError("Wrong number of segments in token")
        return self.tokens[token]


@pytest.fixture
def google(monkeypatch):
    falso = GoogleFalso()
    monkeypatch.setattr(config, "GOOGLE_CLIENT_IDS", [CLIENT_ID_WEB, CLIENT_ID_ANDROID])
    monkeypatch.setattr(google_auth_service, "_decode", falso.decode)
    return falso
