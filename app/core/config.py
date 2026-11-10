import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


DATABASE_URL = _require("DATABASE_URL")
RESEND_API_KEY = _require("RESEND_API_KEY")
EMAIL_FROM = _require("EMAIL_FROM")
SECRET_KEY = _require("SECRET_KEY")

# Cookie de sessão do painel só trafega por HTTPS. Os navegadores aceitam
# cookies "Secure" em http://localhost, então o padrão serve também no
# desenvolvimento. Use "false" só se acessar o painel por outro endereço sem HTTPS.
ADMIN_COOKIE_SECURE = os.getenv("ADMIN_COOKIE_SECURE", "true").lower() != "false"