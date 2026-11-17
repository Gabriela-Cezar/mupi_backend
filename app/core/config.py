"""Configurações do backend, lidas das variáveis de ambiente (arquivo .env).

Todo o código lê as configurações daqui, nunca direto com os.getenv (FAL-18).
"""
import os
from pathlib import Path

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


def _positive_float(name: str, default: float) -> float:
    value = _optional(name)

    if value is None:
        return default

    try:
        number = float(value.replace(",", "."))
    except ValueError:
        raise RuntimeError(f"{name} deve ser um número (metros): {value!r}")

    if number <= 0:
        raise RuntimeError(f"{name} deve ser maior que zero: {value!r}")

    return number


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

# ---------- Login com Google (USR-04) ----------
# Client IDs OAuth do projeto no Google Cloud, separados por vírgula: o do
# Android, o do iOS e o "web" (usado pelo Flutter e pelo navegador). O token
# só é aceito se tiver sido emitido para um deles. Vazio = login com Google
# desligado (a rota responde 503).
GOOGLE_CLIENT_IDS = [
    client_id.strip()
    for client_id in (os.getenv("GOOGLE_CLIENT_IDS") or "").split(",")
    if client_id.strip()
]

# ---------- Abertura do ponto (VIS-02) ----------
# Distância máxima, em metros, entre o usuário e o ponto para abrir o conteúdo
# e registrar a visita. Vale para todos os pontos; ajustar durante o beta.
VISIT_MAX_DISTANCE_M = _positive_float("VISIT_MAX_DISTANCE_M", 25)
# Tolerância ao erro do GPS: soma-se a precisão informada pelo celular, até
# este limite. Ex.: limite 25 m, precisão 10 m → abre a até 35 m; precisão
# 40 m → abre a até 25 + 15 = 40 m.
VISIT_GPS_TOLERANCE_M = _positive_float("VISIT_GPS_TOLERANCE_M", 15)

# ---------- Arquivos (fotos, áudios, imagens de insígnia) no Amazon S3 (INF-04) ----------
# Opcional: sem S3_BUCKET o servidor sobe normalmente, mas o painel recusa o
# envio de arquivos e o app recebe as imagens como ausentes (photo_url nulo).
S3_BUCKET = _optional("S3_BUCKET")
# Região do bucket. Padrão: São Paulo (INF-05).
AWS_REGION = _optional("AWS_REGION") or "sa-east-1"
# Credenciais do usuário IAM da aplicação (só PutObject/GetObject/DeleteObject
# neste bucket). Sem elas, o boto3 procura no ~/.aws/credentials do servidor.
AWS_ACCESS_KEY_ID = _optional("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = _optional("AWS_SECRET_ACCESS_KEY")
# Só para desenvolvimento com um S3 local (ex.: MinIO em Docker). Vazio = AWS.
S3_ENDPOINT_URL = _optional("S3_ENDPOINT_URL")

# ---------- Arquivos numa pasta local (só desenvolvimento) ----------
# Alternativa ao S3 enquanto não há bucket: os arquivos ficam nesta pasta e o
# próprio backend os entrega em /local-files/..., com link assinado e
# temporário como o do S3. Caminho relativo = relativo à raiz do backend.
# NUNCA usar em produção. Não pode ser usado junto com S3_BUCKET.
BACKEND_DIR = Path(__file__).resolve().parents[2]
_local_storage = _optional("LOCAL_STORAGE_DIR")
LOCAL_STORAGE_DIR = (BACKEND_DIR / _local_storage).resolve() if _local_storage else None

if S3_BUCKET and LOCAL_STORAGE_DIR:
    raise RuntimeError(
        "Defina S3_BUCKET ou LOCAL_STORAGE_DIR no .env, não os dois."
    )
