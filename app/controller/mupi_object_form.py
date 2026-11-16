"""Formulário do ponto no painel: leitura, validação e gravação (ADM-04).

Usado pelo cadastro e pela edição. O fluxo é:

1. `read_point_form` lê o que veio do navegador, sem validar (`PointDraft`).
   Se houver erro, é isso que o formulário mostra de volta (ADM-12).
2. `validate_point` confere tudo e devolve os valores prontos (`PointData`),
   ou levanta `FormError` com a mensagem para o administrador.
3. `apply_point` grava os valores num ponto novo ou existente.
"""
import math
from dataclasses import dataclass, field
from types import SimpleNamespace

from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.core.youtube import extract_youtube_id
from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.mupi_object_section import MupiObjectSection
from app.model.mupi_object_video import MupiObjectVideo
from app.model.theme import Theme

MAX_NAME = 150
MAX_SECTION_TITLE = 150
MAX_SECTION_BODY = 20_000
MAX_VIDEO_TITLE = 150
MAX_ADDRESS = 300
MAX_LONG_TEXT = 5_000


class FormError(Exception):
    """Erro de preenchimento: o formulário é mostrado de novo com a mensagem."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------- 1. Leitura (sem validar) ----------

@dataclass
class PointDraft:
    """O que o administrador digitou, no formato que o template usa."""
    name: str = ""
    latitude: str = ""
    longitude: str = ""
    active: bool = True
    standalone: bool = True
    theme_ids: list[str] = field(default_factory=list)
    badge_ids: list[str] = field(default_factory=list)
    sections: list[SimpleNamespace] = field(default_factory=list)
    videos: list[SimpleNamespace] = field(default_factory=list)
    address: str = ""
    opening_hours: str = ""
    accessibility: str = ""
    remove_photo: bool = False
    remove_audio: bool = False
    # Na edição, a foto e o áudio atuais continuam aparecendo
    photo_key: str | None = None
    audio_key: str | None = None
    audio_duration: int | None = None

    # O template marca temas e insígnias por `.id`
    @property
    def themes(self):
        return [SimpleNamespace(id=_int_or_none(i)) for i in self.theme_ids]

    @property
    def badges(self):
        return [SimpleNamespace(id=_int_or_none(i)) for i in self.badge_ids]


def _int_or_none(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pairs(first: list[str], second: list[str]):
    """Junta dois campos repetidos (ex.: título e texto), completando com ""."""
    size = max(len(first), len(second))
    first = list(first) + [""] * (size - len(first))
    second = list(second) + [""] * (size - len(second))
    return zip(first, second)


def _text(form: FormData, name: str) -> str:
    value = form.get(name)
    return value if isinstance(value, str) else ""


def _texts(form: FormData, name: str) -> list[str]:
    return [v for v in form.getlist(name) if isinstance(v, str)]


def _checked(form: FormData, name: str) -> bool:
    return _text(form, name).lower() in ("true", "on", "1")


def read_point_form(form: FormData) -> PointDraft:
    return PointDraft(
        name=_text(form, "name"),
        latitude=_text(form, "latitude"),
        longitude=_text(form, "longitude"),
        active=_checked(form, "active"),
        # Marcado = o ponto só aparece dentro de rotas (PT-09)
        standalone=not _checked(form, "route_only"),
        theme_ids=_texts(form, "theme_ids"),
        badge_ids=_texts(form, "badge_ids"),
        sections=[
            SimpleNamespace(title=t, body=b)
            for t, b in _pairs(_texts(form, "section_title"), _texts(form, "section_body"))
        ],
        videos=[
            SimpleNamespace(url=u, title=t)
            for u, t in _pairs(_texts(form, "video_url"), _texts(form, "video_title"))
        ],
        address=_text(form, "address"),
        opening_hours=_text(form, "opening_hours"),
        accessibility=_text(form, "accessibility"),
        remove_photo=_checked(form, "remove_photo"),
        remove_audio=_checked(form, "remove_audio"),
    )


def draft_from_point(point: MupiObject) -> PointDraft:
    """O ponto salvo, no formato do formulário (tela de edição)."""
    return PointDraft(
        name=point.name,
        latitude=repr(point.latitude),
        longitude=repr(point.longitude),
        active=point.active,
        standalone=point.standalone,
        theme_ids=[str(t.id) for t in point.themes],
        badge_ids=[str(b.id) for b in point.badges],
        sections=[SimpleNamespace(title=s.title, body=s.body) for s in point.sections],
        videos=[SimpleNamespace(url=v.url, title=v.title or "") for v in point.videos],
        address=point.address or "",
        opening_hours=point.opening_hours or "",
        accessibility=point.accessibility or "",
        photo_key=point.photo_key,
        audio_key=point.audio_key,
        audio_duration=point.audio_duration,
    )


# ---------- 2. Validação ----------

@dataclass
class PointData:
    name: str
    latitude: float
    longitude: float
    active: bool
    standalone: bool
    themes: list[Theme]
    badges: list[Badge]
    sections: list[tuple[str, str]]
    videos: list[tuple[str, str | None]]
    address: str | None
    opening_hours: str | None
    accessibility: str | None


def _clean(value: str | None) -> str:
    return (value or "").strip()


def optional_text(value: str | None, field_name: str, max_length: int) -> str | None:
    value = (value or "").replace("\r\n", "\n").strip()

    if len(value) > max_length:
        raise FormError(f"{field_name}: máximo de {max_length} caracteres.")

    return value or None


def _coordinate(value: str, field_name: str, limit: int) -> float:
    text = _clean(value).replace(",", ".")

    if not text:
        raise FormError(f"Informe a {field_name}.")

    try:
        number = float(text)
    except ValueError:
        raise FormError(f"{field_name.capitalize()} inválida: {value}")

    if not math.isfinite(number) or not -limit <= number <= limit:
        raise FormError(f"A {field_name} deve estar entre -{limit} e {limit}.")

    return number


def _ids(values: list[str], field_name: str) -> set[int]:
    ids = set()

    for value in values:
        number = _int_or_none(_clean(value))

        if number is None:
            raise FormError(f"Valor inválido para {field_name}.")

        ids.add(number)

    return ids


def load_themes(db: Session, theme_ids: list[str]) -> list[Theme]:
    ids = _ids(theme_ids, "tema")

    if not ids:
        return []

    themes = db.query(Theme).filter(Theme.id.in_(ids)).all()

    if len(themes) != len(ids):
        raise FormError("Tema não encontrado.")

    return themes


def load_point_badges(db: Session, badge_ids: list[str]) -> list[Badge]:
    ids = _ids(badge_ids, "insígnia")

    if not ids:
        return []

    badges = db.query(Badge).filter(Badge.id.in_(ids)).all()

    if len(badges) != len(ids):
        raise FormError("Uma ou mais insígnias informadas não existem.")

    if any(badge.rule_type != BadgeRule.MANUAL for badge in badges):
        raise FormError(
            "Só insígnias do tipo 'visitar este ponto' podem ser ligadas a um ponto."
        )

    return badges


def validate_sections(drafts: list[SimpleNamespace]) -> list[tuple[str, str]]:
    """Blocos de texto na ordem do formulário (PT-04). Blocos vazios são ignorados."""
    sections = []

    for draft in drafts:
        title = _clean(draft.title)
        # Mantém as quebras de linha do texto; só tira espaços das pontas
        body = (draft.body or "").replace("\r\n", "\n").strip()

        if not title and not body:
            continue

        number = len(sections) + 1

        if not title:
            raise FormError(f"Bloco {number}: informe o título.")

        if not body:
            raise FormError(f"Bloco {number}: escreva o texto.")

        if len(title) > MAX_SECTION_TITLE:
            raise FormError(
                f"Bloco {number}: o título tem no máximo {MAX_SECTION_TITLE} caracteres."
            )

        if len(body) > MAX_SECTION_BODY:
            raise FormError(
                f"Bloco {number}: o texto tem no máximo {MAX_SECTION_BODY} caracteres."
            )

        sections.append((title, body))

    return sections


def validate_videos(drafts: list[SimpleNamespace]) -> list[tuple[str, str | None]]:
    """Vídeos do YouTube na ordem do formulário (PT-07). Linhas vazias são ignoradas."""
    videos = []

    for draft in drafts:
        url = _clean(draft.url)
        title = _clean(draft.title)

        if not url and not title:
            continue

        if not url:
            raise FormError(f"Vídeo \"{title}\": informe o link do YouTube.")

        youtube_id = extract_youtube_id(url)

        if youtube_id is None:
            raise FormError(
                f"Link de vídeo inválido: {url}. Use um link do YouTube "
                "(youtube.com/watch?v=..., youtu.be/... ou youtube.com/shorts/...)."
            )

        if len(title) > MAX_VIDEO_TITLE:
            raise FormError(f"Título do vídeo: máximo de {MAX_VIDEO_TITLE} caracteres.")

        videos.append((youtube_id, title or None))

    return videos


def validate_point(db: Session, draft: PointDraft) -> PointData:
    name = _clean(draft.name)

    if not name:
        raise FormError("Informe o nome do ponto.")

    if len(name) > MAX_NAME:
        raise FormError(f"Nome: máximo de {MAX_NAME} caracteres.")

    return PointData(
        name=name,
        latitude=_coordinate(draft.latitude, "latitude", 90),
        longitude=_coordinate(draft.longitude, "longitude", 180),
        active=draft.active,
        standalone=draft.standalone,
        themes=load_themes(db, draft.theme_ids),
        badges=load_point_badges(db, draft.badge_ids),
        sections=validate_sections(draft.sections),
        videos=validate_videos(draft.videos),
        address=optional_text(draft.address, "Endereço", MAX_ADDRESS),
        opening_hours=optional_text(
            draft.opening_hours, "Horário de funcionamento", MAX_LONG_TEXT
        ),
        accessibility=optional_text(draft.accessibility, "Acessibilidade", MAX_LONG_TEXT),
    )


# ---------- 3. Gravação ----------

def _sync_sections(point: MupiObject, sections: list[tuple[str, str]]) -> None:
    """Reaproveita as linhas existentes na ordem.

    Apagar todas e criar de novo faria o banco ver duas linhas com a mesma
    posição antes de apagar as antigas (restrição única ponto + posição).
    """
    current = list(point.sections)

    for position, (title, body) in enumerate(sections):
        if position < len(current):
            current[position].title = title
            current[position].body = body
        else:
            point.sections.append(
                MupiObjectSection(position=position, title=title, body=body)
            )

    for extra in current[len(sections):]:
        point.sections.remove(extra)


def _sync_videos(point: MupiObject, videos: list[tuple[str, str | None]]) -> None:
    current = list(point.videos)

    for position, (youtube_id, title) in enumerate(videos):
        if position < len(current):
            current[position].youtube_id = youtube_id
            current[position].title = title
        else:
            point.videos.append(
                MupiObjectVideo(position=position, youtube_id=youtube_id, title=title)
            )

    for extra in current[len(videos):]:
        point.videos.remove(extra)


def apply_point(point: MupiObject, data: PointData) -> None:
    point.name = data.name
    point.latitude = data.latitude
    point.longitude = data.longitude
    point.active = data.active
    point.standalone = data.standalone
    point.themes = data.themes
    point.badges = data.badges
    point.address = data.address
    point.opening_hours = data.opening_hours
    point.accessibility = data.accessibility
    _sync_sections(point, data.sections)
    _sync_videos(point, data.videos)
