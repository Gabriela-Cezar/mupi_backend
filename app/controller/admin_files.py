"""Arquivos enviados pelo painel (fotos e imagens de insígnia) e o S3 (INF-04)."""
import logging

from fastapi import HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.file_types import sniff_image_mime
from app.service import storage_service

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024


async def uploaded_file(request: Request, field: str) -> UploadFile | None:
    """Arquivo enviado no campo, ignorando o campo vazio.

    Sem arquivo escolhido, o navegador envia o campo vazio, que chega como
    texto; não pode ser tratado como erro.
    """
    form = await request.form()
    item = form.get(field)

    if isinstance(item, StarletteUploadFile) and item.filename:
        return item

    return None


def read_image(upload: UploadFile) -> tuple[bytes, str]:
    data = upload.file.read(MAX_IMAGE_BYTES + 1)

    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Imagem muito grande (máximo de 5 MB): {upload.filename}"
        )

    mime_type = sniff_image_mime(data)

    if mime_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"Formato não suportado (use PNG, JPEG ou WebP): {upload.filename}"
        )

    return data, mime_type


def store_file(
    db: Session, prefix: str, name: str, data: bytes, content_type: str
) -> str:
    """Envia o arquivo ao S3 e devolve a chave, com erro claro para o painel.

    Se o envio falhar, desfaz o que estava pendente no banco.
    """
    key = storage_service.build_key(prefix, name, content_type)

    try:
        return storage_service.save(key, data, content_type)
    except storage_service.StorageNotConfigured:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Armazenamento de arquivos não configurado (S3_BUCKET)."
        )
    except storage_service.StorageError:
        db.rollback()
        logger.exception("Erro ao enviar arquivo para o S3")
        raise HTTPException(
            status_code=502,
            detail="Não foi possível salvar o arquivo. Tente novamente."
        )


def commit_or_delete_file(db: Session, key: str | None) -> None:
    """Grava no banco; se falhar, apaga o arquivo recém-enviado ao S3."""
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage_service.delete_quietly(key)
        raise


