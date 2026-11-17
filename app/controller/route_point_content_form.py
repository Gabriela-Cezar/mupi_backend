"""Formulário do conteúdo de um ponto dentro de uma rota (painel).

Mesmo fluxo do formulário do ponto (ver mupi_object_form): leitura sem
validar, validação (FormError) e gravação. Reaproveita a validação dos
blocos de texto e dos vídeos do ponto.

Nome em branco = o nome do ponto. Os demais campos substituem os do ponto
para quem está fazendo a rota (vazios = a rota não mostra aquilo).
"""
from dataclasses import dataclass, field
from types import SimpleNamespace

from starlette.datastructures import FormData

from app.controller.mupi_object_form import (
    MAX_ADDRESS,
    MAX_LONG_TEXT,
    MAX_NAME,
    _checked,
    _pairs,
    _text,
    _texts,
    optional_text,
    validate_sections,
    validate_videos,
)
from app.model.mupi_object import MupiObject
from app.model.route_point_content import (
    RoutePointContent,
    RoutePointSection,
    RoutePointVideo,
)


@dataclass
class ContentDraft:
    name: str = ""
    sections: list[SimpleNamespace] = field(default_factory=list)
    videos: list[SimpleNamespace] = field(default_factory=list)
    address: str = ""
    opening_hours: str = ""
    accessibility: str = ""
    remove_photo: bool = False
    remove_audio: bool = False
    photo_key: str | None = None
    audio_key: str | None = None
    audio_duration: int | None = None


def read_content_form(form: FormData) -> ContentDraft:
    return ContentDraft(
        name=_text(form, "name"),
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


def draft_from_content(content: RoutePointContent) -> ContentDraft:
    return ContentDraft(
        name=content.name or "",
        sections=[SimpleNamespace(title=s.title, body=s.body) for s in content.sections],
        videos=[SimpleNamespace(url=v.url, title=v.title or "") for v in content.videos],
        address=content.address or "",
        opening_hours=content.opening_hours or "",
        accessibility=content.accessibility or "",
        photo_key=content.photo_key,
        audio_key=content.audio_key,
        audio_duration=content.audio_duration,
    )


def draft_from_point(point: MupiObject) -> ContentDraft:
    """Ponto ainda sem conteúdo na rota: o formulário começa com os textos e
    vídeos do ponto, para editar a partir deles. Nome, foto e áudio começam
    vazios (= os do ponto, até o administrador trocar)."""
    return ContentDraft(
        sections=[SimpleNamespace(title=s.title, body=s.body) for s in point.sections],
        videos=[SimpleNamespace(url=v.url, title=v.title or "") for v in point.videos],
        address=point.address or "",
        opening_hours=point.opening_hours or "",
        accessibility=point.accessibility or "",
    )


@dataclass
class ContentData:
    name: str | None
    sections: list[tuple[str, str]]
    videos: list[tuple[str, str | None]]
    address: str | None
    opening_hours: str | None
    accessibility: str | None


def validate_content(draft: ContentDraft) -> ContentData:
    return ContentData(
        name=optional_text(draft.name, "Nome", MAX_NAME),
        sections=validate_sections(draft.sections),
        videos=validate_videos(draft.videos),
        address=optional_text(draft.address, "Endereço", MAX_ADDRESS),
        opening_hours=optional_text(draft.opening_hours, "Horário de funcionamento", MAX_LONG_TEXT),
        accessibility=optional_text(draft.accessibility, "Acessibilidade", MAX_LONG_TEXT),
    )


def apply_content(content: RoutePointContent, data: ContentData) -> None:
    content.name = data.name
    content.address = data.address
    content.opening_hours = data.opening_hours
    content.accessibility = data.accessibility

    # Reaproveita as linhas na ordem (restrição única conteúdo + posição)
    current = list(content.sections)
    for position, (title, body) in enumerate(data.sections):
        if position < len(current):
            current[position].title, current[position].body = title, body
        else:
            content.sections.append(RoutePointSection(position=position, title=title, body=body))
    for extra in current[len(data.sections):]:
        content.sections.remove(extra)

    current = list(content.videos)
    for position, (youtube_id, title) in enumerate(data.videos):
        if position < len(current):
            current[position].youtube_id, current[position].title = youtube_id, title
        else:
            content.videos.append(
                RoutePointVideo(position=position, youtube_id=youtube_id, title=title)
            )
    for extra in current[len(data.videos):]:
        content.videos.remove(extra)
