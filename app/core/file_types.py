"""Tipo real dos arquivos enviados, detectado pelo conteúdo.

Nunca confiar no tipo declarado pelo navegador ou na extensão do nome.
"""


def sniff_image_mime(data: bytes) -> str | None:
    """PNG, JPEG ou WebP; None para qualquer outro conteúdo."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None
