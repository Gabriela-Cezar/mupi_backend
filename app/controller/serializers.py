"""Formato das respostas da API do aplicativo.

O ponto MUPI tem duas formas (FAL-06):
- resumo: o que aparece no mapa, nas buscas e nos pontos próximos, mesmo de longe;
- conteúdo: tudo o que o ponto oferece, entregue só ao abrir o ponto estando perto.
"""
from sqlalchemy.orm import selectinload

from app.model.badge import Badge
from app.core.youtube import watch_url
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
        # Rota onde foi conquistada (insígnia de conclusão de rota)
        "collected_at_route": (
            {"id": item.route.id, "name": item.route.name}
            if item.route is not None
            else None
        ),
    }


# ---------- Conteúdo do ponto ----------

def serialize_theme(theme) -> dict:
    return {"id": theme.id, "name": theme.name}


def serialize_section(section) -> dict:
    # Texto limpo, sem marcações: o app formata e pode ler em voz alta (PT-04)
    return {"title": section.title, "body": section.body}


def serialize_video(video) -> dict:
    return {
        "youtube_id": video.youtube_id,
        "title": video.title,
        "url": watch_url(video.youtube_id),
    }


def _photo_url(obj: MupiObject) -> str | None:
    """Link temporário da foto do ponto. Aparece no mapa, mesmo de longe."""
    return storage_service.url(obj.photo_key)


def serialize_audio(obj) -> dict | None:
    """Áudio do ponto (PT-06): link temporário (1 h) e duração em segundos.

    Só vai no conteúdo, entregue na abertura. O link do S3 aceita
    requisições parciais (Range): o app toca sem baixar o arquivo inteiro.
    """
    url = storage_service.url(obj.audio_key, storage_service.AUDIO_URL_SECONDS)

    if url is None:
        return None

    return {"url": url, "duration_seconds": obj.audio_duration}


# ---------- Ponto MUPI ----------

def mupi_load_options():
    return (
        selectinload(MupiObject.badges),
        selectinload(MupiObject.themes),
        selectinload(MupiObject.sections),
        selectinload(MupiObject.videos),
    )


def serialize_summary(
    obj: MupiObject,
    visited: bool,
    distance: float | None = None
) -> dict:
    """Resumo do ponto (PT-10): sem blocos de texto, vídeos nem insígnias."""
    data = {
        "id": obj.id,
        "name": obj.name,
        "latitude": obj.latitude,
        "longitude": obj.longitude,
        "themes": [serialize_theme(t) for t in obj.themes],
        "photo_url": _photo_url(obj),
        "has_video": bool(obj.videos),
        "has_audio": bool(obj.audio_key),
        "address": obj.address,
        "visited": visited,
    }

    if distance is not None:
        data["distance"] = round(distance, 2)

    return data


def serialize_content(obj: MupiObject, route_content=None) -> dict:
    """Conteúdo completo (PT-13): só para quem abriu o ponto estando perto.

    Com [route_content] (o usuário está fazendo uma rota que tem conteúdo
    próprio para o ponto), ele substitui o do ponto: blocos, áudio, vídeos e
    informações do local. Nome e foto em branco na rota = os do ponto. A
    posição e as insígnias são sempre as do ponto.
    """
    source = route_content or obj
    summary = serialize_summary(obj, visited=True)

    if route_content is not None:
        summary.update({
            "name": route_content.name or obj.name,
            "photo_url": (
                storage_service.url(route_content.photo_key)
                if route_content.photo_key else summary["photo_url"]
            ),
            "has_video": bool(route_content.videos),
            "has_audio": bool(route_content.audio_key),
            "address": route_content.address,
        })

    return {
        **summary,
        "sections": [serialize_section(s) for s in source.sections],
        "videos": [serialize_video(v) for v in source.videos],
        "audio": serialize_audio(source),
        "opening_hours": source.opening_hours,
        "accessibility": source.accessibility,
        # Insígnias de visita deste ponto; as desativadas não aparecem
        "badges": [serialize_badge(b) for b in obj.badges if b.active],
        # De qual rota é este conteúdo (null = o conteúdo normal do ponto)
        "route_content": (
            {"route_id": route_content.route_id, "route_name": route_content.route.name}
            if route_content is not None else None
        ),
    }
