"""Tipo real dos arquivos enviados, detectado pelo conteúdo.

Nunca confiar no tipo declarado pelo navegador ou na extensão do nome.
"""
import io
import re


def sniff_image_mime(data: bytes) -> str | None:
    """PNG, JPEG ou WebP; None para qualquer outro conteúdo."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# ---------- Áudio (PT-06) ----------

# Marcas do contêiner MP4 usadas por arquivos de áudio (M4A/AAC)
_MP4_BRANDS = {b"M4A ", b"M4B ", b"mp42", b"mp41", b"isom", b"iso2", b"dash"}

# Caixa "hdlr" de uma faixa de vídeo dentro do MP4
_MP4_VIDEO_TRACK = re.compile(rb"hdlr.{8}vide", re.DOTALL)


def _is_mp3_frame(data: bytes) -> bool:
    """Cabeçalho de quadro MPEG de áudio (camada III) sem a etiqueta ID3."""
    if len(data) < 4 or data[0] != 0xFF or (data[1] & 0xE0) != 0xE0:
        return False

    version = (data[1] >> 3) & 0b11   # 01 = reservado
    layer = (data[1] >> 1) & 0b11     # 01 = camada III
    bitrate = data[2] >> 4            # 0000 = livre, 1111 = inválido
    sample_rate = (data[2] >> 2) & 0b11

    return version != 0b01 and layer == 0b01 and bitrate not in (0, 15) and sample_rate != 0b11


def sniff_audio_mime(data: bytes) -> str | None:
    """MP3 ou M4A/AAC; None para qualquer outro conteúdo (inclusive vídeo MP4)."""
    if data.startswith(b"ID3") or _is_mp3_frame(data):
        return "audio/mpeg"

    if data[4:8] == b"ftyp" and data[8:12] in _MP4_BRANDS:
        # MP4 com vídeo não é áudio, mesmo que também tenha som
        if _MP4_VIDEO_TRACK.search(data):
            return None
        return "audio/mp4"

    return None


def audio_duration_seconds(data: bytes, mime_type: str) -> int | None:
    """Duração em segundos (arredondada), lida do próprio arquivo.

    None se o arquivo não puder ser lido como áudio desse formato
    (corrompido ou só com o começo certo).
    """
    # Importado aqui: só o envio de áudio pelo painel precisa do mutagen
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4

    reader = MP3 if mime_type == "audio/mpeg" else MP4

    try:
        length = reader(io.BytesIO(data)).info.length
    except Exception:
        # O mutagen levanta erros variados para arquivo corrompido
        return None

    if not length or length <= 0:
        return None

    return max(1, round(length))
