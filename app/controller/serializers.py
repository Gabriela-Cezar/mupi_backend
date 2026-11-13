"""Formato das respostas da API do aplicativo.

O ponto MUPI tem duas formas (FAL-06):
- resumo: o que aparece no mapa, nas buscas e nos pontos próximos, mesmo de longe;
- conteúdo: tudo o que o ponto oferece, entregue só ao abrir o ponto estando perto.
"""
from sqlalchemy.orm import selectinload

from app.model.badge import Badge
from app.model.midia import MediaType, MupiObjectMedia
from app.model.mupi_object import MupiObject
from app.model.user_badge import UserBadge
from app.service import storage_service


# ---------- Insígnias ----------

def serialize_badge(badge: Badge) -> dict:
    return {
        "id": badge.id,
        "name": badge.name,
        "description": badge.description,
        # Link temporário do S3 (INF-04)
        "image_url": storage_service.url(badge.image_key),
    }


def serialize_rule(badge: Badge) -> dict:
    return {
        "type": badge.rule_type.value,
        "required_count": badge.required_count,
        "theme": (
            {"id": badge.theme.id, "name": badge.theme.name}
            if badge.theme is not None
            else None
        ),
    }


def serialize_badge_full(badge: Badge) -> dict:
    return {**serialize_badge(badge), "rule": serialize_rule(badge)}


def serialize_collected(item: UserBadge) -> dict:
    return {
        **serialize_badge_full(item.badge),
        "collected_at": item.collected_at.isoformat(),
        "collected_at_object": (
            {"id": item.mupi_object.id, "name": item.mupi_object.name}
            if item.mupi_object is not None
            else None
        ),
    }


# ---------- Mídias ----------

def serialize_media(media: MupiObjectMedia) -> dict:
    # Só vídeos: a foto do ponto fica em photo_url
    return {
        "id": media.id,
        "object_id": media.object_id,
        "type": media.type.value,
        "url": media.url,
        "title": media.title,
        "description": media.description,
    }


def _photo_url(obj: MupiObject) -> str | None:
    """Link temporário da foto do ponto. Aparece no mapa, mesmo de longe."""
    return storage_service.url(obj.photo_key)


# ---------- Ponto MUPI ----------

def mupi_load_options():
    return (
        selectinload(MupiObject.badges),
        selectinload(MupiObject.media),
        selectinload(MupiObject.theme),
    )


def serialize_summary(
    obj: MupiObject,
    visited: bool,
    distance: float | None = None
) -> dict:
    """Resumo do ponto: sem texto, vídeos nem insígnias."""
    data = {
        "id": obj.id,
        "name": obj.name,
        "latitude": obj.latitude,
        "longitude": obj.longitude,
        "theme": (
            {"id": obj.theme.id, "name": obj.theme.name}
            if obj.theme is not None
            else None
        ),
        "photo_url": _photo_url(obj),
        "has_video": any(m.type == MediaType.VIDEO for m in obj.media),
        "visited": visited,
    }

    if distance is not None:
        data["distance"] = round(distance, 2)

    return data


def serialize_content(obj: MupiObject) -> dict:
    """Conteúdo completo: só para quem abriu o ponto estando perto."""
    return {
        **serialize_summary(obj, visited=True),
        "description": obj.description,
        "media": [serialize_media(m) for m in obj.media],
        "badges": [serialize_badge(b) for b in obj.badges],
    }
