import logging
import math
import os
from urllib.parse import urlparse

import polyline
import requests
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database.database import get_db
from app.model.badge import Badge, BadgeRule
from app.model.theme import Theme
from app.model.midia import MediaType, MupiObjectMedia
from app.model.mupi_object import MupiObject
from app.model.mupi_object_badge import MupiObjectBadge  # noqa: F401  (registra a tabela de associação)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Administração"]
)

mupi_object_api_router = APIRouter(
    prefix="/mupi-objects",
    tags=["Objetos MUPI"]
)

templates = Jinja2Templates(
    directory="app/templates"
)

EARTH_RADIUS_M = 6_371_000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_URL_LENGTH = 500


# ---------- Helpers ----------
def parse_optional_int(value: str | None, field: str) -> int | None:
    # Formulários HTML mandam "" para campos numéricos vazios
    value = (value or "").strip()

    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Valor inválido para {field}."
        )
        
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bounding_box(lat: float, lon: float, radius_m: float):
    # Aproximação adequada para uso local (não trata o antimeridiano)
    delta_lat = math.degrees(radius_m / EARTH_RADIUS_M)
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    delta_lon = math.degrees(radius_m / (EARTH_RADIUS_M * cos_lat))

    return lat - delta_lat, lat + delta_lat, lon - delta_lon, lon + delta_lon


def serialize_badge(badge: Badge) -> dict:
    return {
        "id": badge.id,
        "name": badge.name,
        "description": badge.description,
        # image_mime_type só existe quando há imagem, então não carrega o blob
        "image_url": (
            f"/mupi-objects/badges/{badge.id}/image"
            if badge.image_mime_type
            else None
        ),
    }


def serialize_media(media: MupiObjectMedia) -> dict:
    # Sem url significa que o binário está no banco (data XOR url)
    return {
        "id": media.id,
        "object_id": media.object_id,
        "type": media.type.value,
        "url": media.url or f"/mupi-objects/media/{media.id}",
        "title": media.title,
        "description": media.description,
    }


def serialize_object(obj: MupiObject, distance: float | None = None) -> dict:
    data = {
        "id": obj.id,
        "name": obj.name,
        "description": obj.description,
        "latitude": obj.latitude,
        "longitude": obj.longitude,
        "active": obj.active,
        "badges": [serialize_badge(b) for b in obj.badges],
        "media": [serialize_media(m) for m in obj.media],
    }

    if distance is not None:
        data["distance"] = round(distance, 2)

    return data


def object_load_options():
     return (
        selectinload(MupiObject.badges),
        selectinload(MupiObject.media),
    )

def sniff_image_mime(data: bytes) -> str | None:
    """Detecta o tipo real pelo conteúdo, sem confiar no que o cliente declarou."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
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


def is_valid_http_url(url: str) -> bool:
    if len(url) > MAX_VIDEO_URL_LENGTH:
        return False

    parsed = urlparse(url)

    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


# ---------- API pública: objetos ----------

@mupi_object_api_router.get("")
def get_mupi_objects(
    db: Session = Depends(get_db)
):
    objects = (
        db.query(MupiObject)
        .options(*object_load_options())
        .filter(MupiObject.active.is_(True))
        .all()
    )

    return [serialize_object(obj) for obj in objects]


@mupi_object_api_router.get("/nearby")
def get_nearby_mupi_objects(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius: float = Query(..., gt=0, le=50_000),
    db: Session = Depends(get_db)
):
    min_lat, max_lat, min_lng, max_lng = bounding_box(latitude, longitude, radius)

    objects = (
        db.query(MupiObject)
        .options(*object_load_options())
        .filter(
            MupiObject.active.is_(True),
            MupiObject.latitude.between(min_lat, max_lat),
            MupiObject.longitude.between(min_lng, max_lng),
        )
        .all()
    )

    results = []

    for obj in objects:
        distance = haversine_m(latitude, longitude, obj.latitude, obj.longitude)

        if distance <= radius:
            results.append(serialize_object(obj, distance))

    results.sort(key=lambda item: item["distance"])

    return results


@mupi_object_api_router.get("/search")
def search_mupi_objects(
    name: str = Query(..., min_length=1, max_length=100),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db)
):
    objects = (
        db.query(MupiObject)
        .options(*object_load_options())
        .filter(
            MupiObject.active.is_(True),
            MupiObject.name.ilike(f"%{name}%"),
        )
        .limit(50)
        .all()
    )

    results = [
        serialize_object(
            obj,
            haversine_m(latitude, longitude, obj.latitude, obj.longitude)
        )
        for obj in objects
    ]

    results.sort(key=lambda item: item["distance"])

    return results


@mupi_object_api_router.get("/{object_id}/route")
def get_mupi_route(
    object_id: int,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db)
):
    mupi = (
        db.query(MupiObject)
        .filter(
            MupiObject.id == object_id,
            MupiObject.active.is_(True)
        )
        .first()
    )

    if not mupi:
        raise HTTPException(
            status_code=404,
            detail="MUPI não encontrado."
        )

    api_key = os.getenv("OPENROUTESERVICE_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Chave da API de roteamento não configurada."
        )

    url = (
        "https://api.heigit.org/"
        "openrouteservice/v2/directions/"
        "foot-walking"
    )

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    body = {
        "coordinates": [
            [longitude, latitude],
            [mupi.longitude, mupi.latitude]
        ],
        "geometry": True
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=20
        )
    except requests.RequestException:
        logger.exception("Erro de conexão com o serviço de rota")

        raise HTTPException(
            status_code=502,
            detail="Não foi possível conectar ao serviço de roteamento."
        )

    if response.status_code != 200:
        logger.warning(
            "Serviço de rota respondeu %s: %s",
            response.status_code,
            response.text
        )

        raise HTTPException(
            status_code=502,
            detail={
                "message": "Erro ao calcular a rota.",
                "provider_status": response.status_code
            }
        )

    routes = response.json().get("routes") or []

    if not routes:
        raise HTTPException(
            status_code=502,
            detail="O serviço de rota não retornou nenhum caminho."
        )

    route = routes[0]
    coordinates = polyline.decode(route["geometry"])

    return {
        "mupi_id": mupi.id,
        "distance": route["summary"]["distance"],
        "duration": route["summary"]["duration"],
        "coordinates": [
            [lng, lat]
            for lat, lng in coordinates
        ]
    }


@mupi_object_api_router.get("/badges/{badge_id}/image")
def get_badge_image(
    badge_id: int,
    db: Session = Depends(get_db)
):
    badge = (
        db.query(Badge)
        .filter(Badge.id == badge_id)
        .first()
    )

    if not badge or not badge.image:
        return Response(status_code=404)

    return Response(
        content=badge.image,
        media_type=badge.image_mime_type or "image/png",
        headers={"Cache-Control": "public, max-age=86400"}
    )


@mupi_object_api_router.get("/{object_id}/image")
def get_mupi_object_image(
    object_id: int,
    db: Session = Depends(get_db)
):
    media = (
        db.query(MupiObjectMedia)
        .filter(
            MupiObjectMedia.object_id == object_id,
            MupiObjectMedia.type == MediaType.IMAGE,
            MupiObjectMedia.data.isnot(None)
        )
        .order_by(MupiObjectMedia.id)
        .first()
    )

    if not media:
        return Response(status_code=404)

    return Response(
        content=media.data,
        media_type=media.mime_type or "image/png",
        headers={"Cache-Control": "public, max-age=3600"}
    )


# ---------- Admin (ainda sem autenticação) ----------

@router.get("/search")
def admin_search_mupi_objects(
    name: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db)
):
    objects = (
        db.query(MupiObject)
        .filter(MupiObject.name.ilike(f"%{name}%"))
        .limit(50)
        .all()
    )

    return [
        {
            "id": obj.id,
            "name": obj.name,
            "description": obj.description,
            "latitude": obj.latitude,
            "longitude": obj.longitude,
            "active": obj.active
        }
        for obj in objects
    ]


@router.get("/mupi-objects")
def mupi_object_form(
    request: Request,
    db: Session = Depends(get_db)
):
    badges = db.query(Badge).all()

    return templates.TemplateResponse(
        request=request,
        name="admin/mupi_object_form.html",
        context={
            "badges": badges
        }
    )


@router.post("/mupi-objects")
def create_mupi_object(
    name: str = Form(..., max_length=150),
    description: str = Form(None),
    latitude: float = Form(..., ge=-90, le=90),
    longitude: float = Form(..., ge=-180, le=180),
    active: bool = Form(False),
    badge_ids: list[int] = Form([]),
    video_urls: str = Form(""),
    images: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
    theme_id: str = Form(""),
):
    # Validações primeiro, antes de tocar no banco
    badges = []
    
    parsed_theme_id = parse_optional_int(theme_id, "tema")

    if parsed_theme_id is not None and db.get(Theme, parsed_theme_id) is None:
        raise HTTPException(
            status_code=400,
            detail="Tema não encontrado."
        )

    if badge_ids:
        badges = (
            db.query(Badge)
            .filter(Badge.id.in_(badge_ids))
            .all()
        )

        if len(badges) != len(set(badge_ids)):
            raise HTTPException(
                status_code=400,
                detail="Uma ou mais insígnias informadas não existem."
            )

    media_items = []

    for image in images:
        if not image.filename:
            continue

        image_data, mime_type = read_image(image)

        media_items.append(
            MupiObjectMedia(
                type=MediaType.IMAGE,
                data=image_data,
                mime_type=mime_type,
                title=image.filename[:150]
            )
        )

    for line in video_urls.splitlines():
        url = line.strip()

        if not url:
            continue

        if not is_valid_http_url(url):
            raise HTTPException(
                status_code=400,
                detail=f"URL de vídeo inválida: {url}"
            )

        media_items.append(
            MupiObjectMedia(
                type=MediaType.VIDEO,
                url=url
            )
        )

    mupi_object = MupiObject(
        name=name,
        description=description,
        latitude=latitude,
        longitude=longitude,
        active=active,
        media=media_items,
        badges=badges
    )

    db.add(mupi_object)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(mupi_object)

    return {
        "message": "Objeto MUPI cadastrado com sucesso!",
        "id": mupi_object.id
    }


@router.get("/badges")
def badge_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/badge_form.html"
    )


@router.post("/badges")
def create_badge(
    name: str = Form(..., max_length=100),
    description: str = Form(None),
    rule_type: str = Form("manual"),
    required_count: str = Form(""),
    theme_id: str = Form(""),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    try:
        rule = BadgeRule(rule_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Tipo de regra inválido."
        )

    count = parse_optional_int(required_count, "quantidade")
    theme = parse_optional_int(theme_id, "tema")

    if rule == BadgeRule.MANUAL:
        count, theme = None, None
    else:
        if count is None or count < 1:
            raise HTTPException(
                status_code=400,
                detail="Informe a quantidade de MUPIs a visitar (mínimo 1)."
            )

        if rule == BadgeRule.VISIT_COUNT:
            theme = None
        elif theme is None or db.get(Theme, theme) is None:
            raise HTTPException(
                status_code=400,
                detail="Selecione um tema válido para esta regra."
            )

    image_data = None
    image_mime_type = None

    if image and image.filename:
        image_data, image_mime_type = read_image(image)

    badge = Badge(
        name=name,
        description=description,
        image=image_data,
        image_mime_type=image_mime_type,
        rule_type=rule,
        required_count=count,
        theme_id=theme
    )

    db.add(badge)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail="Já existe uma insígnia com esse nome."
        )

    db.refresh(badge)

    return {
        "message": "Insígnia cadastrada com sucesso!",
        "id": badge.id
    }
    
@mupi_object_api_router.get("/media/{media_id}")
def get_media_file(
    media_id: int,
    db: Session = Depends(get_db)
):
    media = (
        db.query(MupiObjectMedia)
        .join(MupiObject, MupiObject.id == MupiObjectMedia.object_id)
        .filter(
            MupiObjectMedia.id == media_id,
            MupiObjectMedia.data.isnot(None),
            MupiObject.active.is_(True),
        )
        .first()
    )

    if not media:
        return Response(status_code=404)

    return Response(
        content=media.data,
        media_type=media.mime_type or "image/png",
        headers={"Cache-Control": "public, max-age=3600"}
    )