"""Entrega os arquivos da pasta local (só desenvolvimento, LOCAL_STORAGE_DIR).

Faz o papel do link assinado do S3: só responde com `expires` e `signature`
gerados pelo storage_service.url, e só enquanto o link vale. Sem a pasta
local configurada, a rota não existe (404).
"""
import mimetypes

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.service import storage_service

router = APIRouter(prefix=storage_service.LOCAL_FILES_PATH, include_in_schema=False)


@router.get("/{key:path}")
def local_file(
    key: str,
    expires: str = Query(""),
    signature: str = Query(""),
):
    if not storage_service.is_local():
        raise HTTPException(status_code=404)

    # Como o bucket privado: sem link assinado válido, acesso negado
    if not storage_service.check_local_link(key, expires, signature):
        raise HTTPException(status_code=403, detail="Link inválido ou expirado.")

    try:
        path = storage_service.local_path(key)
    except ValueError:
        raise HTTPException(status_code=404)

    if not path.is_file():
        raise HTTPException(status_code=404)

    return FileResponse(
        path,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=86400"},
    )
