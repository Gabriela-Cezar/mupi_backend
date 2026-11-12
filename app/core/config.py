"""Configurações do backend, lidas das variáveis de ambiente (arquivo .env).

Todo o código lê as configurações daqui, nunca direto com os.getenv (FAL-18).
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


def _optional(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


DATABASE_URL = _require("DATABASE_URL")
RESEND_API_KEY = _require("RESEND_API_KEY")
EMAIL_FROM = _require("EMAIL_FROM")
SECRET_KEY = _require("SECRET_KEY")

# Cookie de sessão do painel só trafega por HTTPS. Os navegadores aceitam
# cookies "Secure" em http://localhost, então o padrão serve também no
# desenvolvimento. Use "false" só se acessar o painel por outro endereço sem HTTPS.
ADMIN_COOKIE_SECURE = os.getenv("ADMIN_COOKIE_SECURE", "true").lower() != "false"

# Sites que podem chamar a API pelo navegador (FAL-09). Vazio = nenhum.
# O app de celular e o painel não precisam disto; é para o Flutter web no
# desenvolvimento ou um futuro painel em outro domínio. Ver app/core/cors.py.
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGIN_REGEX = os.getenv("CORS_ALLOWED_ORIGIN_REGEX") or None

# Chave do OpenRouteService, usada para traçar a rota a pé até o ponto
# (botão "Como chegar"). Opcional: sem ela o servidor sobe normalmente,
# e só essa rota responde com erro explicando que falta a chave.
OPENROUTESERVICE_API_KEY = _optional("OPENROUTESERVICE_API_KEY")
