"""Quais sites podem chamar a API a partir do navegador (FAL-09).

O app de celular não passa por CORS e o painel é servido pelo próprio
backend; por isso, por padrão, nenhum site de fora é liberado. As origens
permitidas vêm do .env (`CORS_ALLOWED_ORIGINS` e `CORS_ALLOWED_ORIGIN_REGEX`).
"""
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Exemplo para o desenvolvimento: o Flutter web (Chrome) roda em
# localhost com uma porta diferente a cada execução
LOCAL_DEV_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$"


def parse_origins(value: str | None) -> list[str]:
    """'https://a.com, https://b.com' -> ['https://a.com', 'https://b.com']."""
    return [origin.strip() for origin in (value or "").split(",") if origin.strip()]


def validate_cors_settings(origins: list[str], origin_regex: str | None) -> None:
    if "*" in origins:
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS não pode ser '*': qualquer site poderia "
            "usar a API pelo navegador de quem está logado. Liste os "
            "endereços permitidos (ex.: https://painel.mupi.com.br)."
        )

    for origin in origins:
        if not origin.startswith(("http://", "https://")) or origin.endswith("/"):
            raise RuntimeError(
                f"Origem CORS inválida: {origin!r}. Use o formato "
                "https://dominio.com (com protocolo e sem barra no final)."
            )

    if origin_regex:
        try:
            re.compile(origin_regex)
        except re.error as error:
            raise RuntimeError(f"CORS_ALLOWED_ORIGIN_REGEX inválido: {error}")


def add_cors(app: FastAPI, origins: list[str], origin_regex: str | None) -> None:
    validate_cors_settings(origins, origin_regex)

    if not origins and not origin_regex:
        return  # nenhum site de fora liberado

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=origin_regex,
        # O app usa o token no cabeçalho, não cookies; o cookie do painel
        # nunca deve ser enviado por outro site
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        # Permite ao app no navegador ler o tempo de espera dos erros 429
        expose_headers=["Retry-After"],
        max_age=600,
    )
