"""Arquivos do MUPI no Amazon S3 (INF-04).

Única camada que fala com o S3: salvar, gerar link e apagar. O banco guarda
só a chave (o caminho do arquivo no bucket).

O bucket é privado. O app recebe links temporários assinados:
- fotos, capas e imagens de insígnia: válidos por 24 h (IMAGE_URL_SECONDS);
- áudio: válido por 1 h, entregue só na abertura do ponto (AUDIO_URL_SECONDS).

Desenvolvimento sem S3: com LOCAL_STORAGE_DIR no .env, os arquivos ficam numa
pasta local e o backend os entrega em /local-files/<chave>?expires=&signature=
(link relativo, assinado com a SECRET_KEY e temporário, como o do S3). Ver
app/controller/local_files_controller.py.
"""
import hashlib
import hmac
import re
import threading
import time
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core import config

LOCAL_FILES_PATH = "/local-files"

# Chave segura para virar caminho na pasta local: partes com letras, números,
# ponto, hífen e sublinhado, sem "." nem ".." (nada de sair da pasta)
_SAFE_KEY = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*(/[A-Za-z0-9_-][A-Za-z0-9._-]*)*")

IMAGE_URL_SECONDS = 24 * 60 * 60
AUDIO_URL_SECONDS = 60 * 60

# Extensão do arquivo a partir do tipo (o tipo é sempre detectado pelo conteúdo)
EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
}


class StorageNotConfigured(RuntimeError):
    """S3_BUCKET não foi definido no .env."""


class StorageError(RuntimeError):
    """O S3 recusou ou não respondeu."""


_client = None
_client_lock = threading.Lock()

# Links já gerados, para devolver o mesmo link enquanto ele ainda vale bastante.
# Um link novo a cada chamada faria o app baixar a mesma foto de novo a cada
# recarga do mapa (o cache de imagens do celular usa o link como chave).
_url_cache: dict[tuple[str, int], tuple[str, float]] = {}


def is_configured() -> bool:
    return bool(config.S3_BUCKET) or is_local()


def is_local() -> bool:
    """Arquivos numa pasta local em vez do S3 (só desenvolvimento)."""
    return config.LOCAL_STORAGE_DIR is not None


def local_path(key: str) -> Path:
    """Caminho do arquivo na pasta local. ValueError se a chave não é segura."""
    if not _SAFE_KEY.fullmatch(key):
        raise ValueError(f"Chave inválida: {key!r}")

    root = Path(config.LOCAL_STORAGE_DIR)
    path = (root / key).resolve()

    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Chave inválida: {key!r}")

    return path


def local_signature(key: str, expires: int) -> str:
    message = f"{key}\n{expires}".encode()
    return hmac.new(config.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def check_local_link(key: str, expires: str, signature: str) -> bool:
    """O link local foi gerado por este servidor e ainda vale?"""
    try:
        expires_at = int(expires)
    except (TypeError, ValueError):
        return False

    if expires_at < time.time():
        return False

    return hmac.compare_digest(local_signature(key, expires_at), signature or "")


def _bucket() -> str:
    if not config.S3_BUCKET:
        raise StorageNotConfigured(
            "Armazenamento de arquivos não configurado (S3_BUCKET)."
        )
    return config.S3_BUCKET


def _s3():
    global _client

    with _client_lock:
        if _client is None:
            _client = boto3.client(
                "s3",
                region_name=config.AWS_REGION,
                # Endereço regional (bucket.s3.sa-east-1.amazonaws.com). Com o
                # global, a AWS redireciona buckets fora de us-east-1 e o link
                # assinado deixa de valer depois do redirecionamento.
                endpoint_url=(
                    config.S3_ENDPOINT_URL
                    or f"https://s3.{config.AWS_REGION}.amazonaws.com"
                ),
                aws_access_key_id=config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
                config=Config(
                    # Assinatura v4, exigida em sa-east-1 e nas regiões novas
                    signature_version="s3v4",
                    # bucket no nome do host, não no caminho; com S3 local
                    # (MinIO) o bucket vai no caminho
                    s3={"addressing_style": "path" if config.S3_ENDPOINT_URL else "virtual"},
                    retries={"max_attempts": 3},
                ),
            )
        return _client


def reset() -> None:
    """Esquece o cliente e os links guardados (usado ao trocar a configuração e nos testes)."""
    global _client

    with _client_lock:
        _client = None
    _url_cache.clear()


def build_key(prefix: str, name: str, content_type: str) -> str:
    """Ex.: build_key("points/7", "photo", "image/jpeg") → "points/7/photo-<uuid>.jpg".

    O uuid faz cada envio ter um endereço novo: substituir a foto nunca
    devolve a antiga por causa de cache.
    """
    extension = EXTENSIONS.get(content_type, "bin")
    return f"{prefix}/{name}-{uuid.uuid4().hex}.{extension}"


def save(key: str, data: bytes, content_type: str) -> str:
    """Envia o arquivo para o bucket e devolve a chave."""
    if is_local():
        try:
            path = local_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except (OSError, ValueError) as exc:
            raise StorageError("Não foi possível salvar o arquivo.") from exc
        return key

    bucket = _bucket()

    try:
        _s3().put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="private, max-age=86400",
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageError("Não foi possível salvar o arquivo.") from exc

    return key


def url(key: str | None, expires_in: int = IMAGE_URL_SECONDS) -> str | None:
    """Link temporário para baixar o arquivo, ou None se não há arquivo.

    Gerar o link é um cálculo local (não chama a AWS). Se o S3 não estiver
    configurado, devolve None: o app mostra a imagem padrão.
    """
    if not key or not is_configured():
        return None

    now = time.time()
    cached = _url_cache.get((key, expires_in))

    # Reaproveita enquanto o link ainda tem mais da metade da validade
    if cached and now - cached[1] < expires_in / 2:
        return cached[0]

    if is_local():
        expires_at = int(now) + expires_in
        link = (
            f"{LOCAL_FILES_PATH}/{key}"
            f"?expires={expires_at}&signature={local_signature(key, expires_at)}"
        )
        _url_cache[(key, expires_in)] = (link, now)
        return link

    try:
        link = _s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": _bucket(), "Key": key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError):
        return None

    _url_cache[(key, expires_in)] = (link, now)
    return link


def delete(key: str | None) -> None:
    """Apaga o arquivo. Não falha se ele já não existir."""
    if not key:
        return

    if is_local():
        try:
            local_path(key).unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            raise StorageError("Não foi possível apagar o arquivo.") from exc
    else:
        try:
            _s3().delete_object(Bucket=_bucket(), Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Não foi possível apagar o arquivo.") from exc

    for cache_key in [k for k in _url_cache if k[0] == key]:
        _url_cache.pop(cache_key, None)


def delete_quietly(key: str | None) -> None:
    """Apaga sem levantar erro: para desfazer um envio quando o banco falha."""
    try:
        delete(key)
    except (StorageError, StorageNotConfigured):
        pass
