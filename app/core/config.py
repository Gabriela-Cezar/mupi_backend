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