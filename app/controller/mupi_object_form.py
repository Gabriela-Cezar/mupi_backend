"""Leitura e validação dos campos do formulário do ponto (ADM-04).

Usado pelo cadastro e pela edição. Cada função recebe o que veio do
formulário e devolve os objetos prontos, ou erro 400 com uma mensagem para o
administrador.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.youtube import extract_youtube_id
from app.model.badge import Badge, BadgeRule
from app.model.mupi_object_section import MupiObjectSection
from app.model.mupi_object_video import MupiObjectVideo
from app.model.theme import Theme

MAX_SECTION_TITLE = 150
MAX_SECTION_BODY = 20_000
MAX_VIDEO_TITLE = 150
MAX_ADDRESS = 300
MAX_LONG_TEXT = 5_000


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def clean(value: str | None) -> str:
    return (value or "").strip()


def optional_text(value: str | None, field: str, max_length: int) -> str | None:
    value = clean(value)

    if len(value) > max_length:
        raise bad_request(f"{field}: máximo de {max_length} caracteres.")

    return value or None


def load_themes(db: Session, theme_ids: list[int]) -> list[Theme]:
    ids = set(theme_ids)

    if not ids:
        return []

    themes = db.query(Theme).filter(Theme.id.in_(ids)).all()

    if len(themes) != len(ids):
        raise bad_request("Tema não encontrado.")

    return themes


def load_point_badges(db: Session, badge_ids: list[int]) -> list[Badge]:
    ids = set(badge_ids)

    if not ids:
        return []

    badges = db.query(Badge).filter(Badge.id.in_(ids)).all()

    if len(badges) != len(ids):
        raise bad_request("Uma ou mais insígnias informadas não existem.")

    if any(badge.rule_type != BadgeRule.MANUAL for badge in badges):
        raise bad_request(
            "Só insígnias do tipo 'visitar este ponto' podem ser ligadas a um ponto."
        )

    return badges


def _pairs(first: list[str], second: list[str]):
    """Junta duas listas de campos repetidos, completando a menor com ""."""
    size = max(len(first), len(second))
    first = list(first) + [""] * (size - len(first))
    second = list(second) + [""] * (size - len(second))
    return zip(first, second)


def build_sections(titles: list[str], bodies: list[str]) -> list[MupiObjectSection]:
    """Blocos de texto na ordem do formulário (PT-04). Blocos vazios são ignorados."""
    sections = []

    for title, body in _pairs(titles, bodies):
        title = clean(title)
        # Mantém as quebras de linha do texto; só tira espaços das pontas
        body = (body or "").replace("\r\n", "\n").strip()

        if not title and not body:
            continue

        number = len(sections) + 1

        if not title:
            raise bad_request(f"Bloco {number}: informe o título.")

        if not body:
            raise bad_request(f"Bloco {number}: escreva o texto.")

        if len(title) > MAX_SECTION_TITLE:
            raise bad_request(
                f"Bloco {number}: o título tem no máximo {MAX_SECTION_TITLE} caracteres."
            )

        if len(body) > MAX_SECTION_BODY:
            raise bad_request(
                f"Bloco {number}: o texto tem no máximo {MAX_SECTION_BODY} caracteres."
            )

        sections.append(
            MupiObjectSection(position=len(sections), title=title, body=body)
        )

    return sections


def build_videos(urls: list[str], titles: list[str]) -> list[MupiObjectVideo]:
    """Vídeos do YouTube na ordem do formulário (PT-07). Linhas vazias são ignoradas."""
    videos = []

    for url, title in _pairs(urls, titles):
        url = clean(url)
        title = clean(title)

        if not url and not title:
            continue

        if not url:
            raise bad_request(f"Vídeo \"{title}\": informe o link do YouTube.")

        youtube_id = extract_youtube_id(url)

        if youtube_id is None:
            raise bad_request(
                f"Link de vídeo inválido: {url}. Use um link do YouTube "
                "(youtube.com/watch?v=..., youtu.be/... ou youtube.com/shorts/...)."
            )

        if len(title) > MAX_VIDEO_TITLE:
            raise bad_request(
                f"Título do vídeo: máximo de {MAX_VIDEO_TITLE} caracteres."
            )

        videos.append(
            MupiObjectVideo(
                position=len(videos), youtube_id=youtube_id, title=title or None
            )
        )

    return videos
