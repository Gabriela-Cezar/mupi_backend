import logging
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
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy.orm import Session

from app.controller.serializers import (
    mupi_load_options,
    serialize_collected,
    serialize_content,
    serialize_summary,
)
from app.core.admin_auth import require_admin_with_csrf
from app.core.dependencies import get_current_user
from app.core.templates import templates
from app.database.database import get_db
from app.model.badge import Badge, BadgeRule
from app.model.theme import Theme
from app.model.midia import MediaType, MupiObjectMedia
from app.model.mupi_object import MupiObject
from app.model.mupi_object_badge import MupiObjectBadge  # noqa: F401  (registra a tabela de associação)
from app.model.user import User
from app.model.user_visit import UserVisit
from app.service.badge_service import register_visit, visit_counts
from app.service.proximity_service import (
    bounding_box,
    get_active_mupi,
    get_mupi_in_range,
    haversine_m,
)


logger = logging.getLogger(__name__)

# Todas as rotas do painel exigem login (e token CSRF nos envios)
router = APIRouter(
    prefix="/admin",
    tags=["Administração"],
    dependencies=[Depends(require_admin_with_csrf)]
)

# Rotas do aplicativo: todas exigem login (USR-10 / FAL-06)
mupi_object_api_router = APIRouter(
    prefix="/mupi-objects",
    tags=["Objetos MUPI"],
    dependencies=[Depends(get_current_user)]
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_URL_LENGTH = 500


def parse_optional_int(value: str | None, field: str) -> int | None:
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


# ---------- API do app: resumo (mapa, próximos, busca) ----------

def visited_ids(db: Session, user_id: int) -> set[int]:
    return {
        object_id
        for (object_id,) in db.query(UserVisit.object_id)
        .filter(UserVisit.user_id == user_id)
    }


@mupi_object_api_router.get("")
def get_mupi_objects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    objects = (
        db.query(MupiObject)
        .options(*mupi_load_options())
        .filter(MupiObject.active.is_(True))
        .order_by(MupiObject.name)
        .all()
    )

    visited = visited_ids(db, user.id)

    return [serialize_summary(obj, obj.id in visited) for obj in objects]


@mupi_object_api_router.get("/nearby")
def get_nearby_mupi_objects(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius: float = Query(..., gt=0, le=50_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    min_lat, max_lat, min_lng, max_lng = bounding_box(latitude, longitude, radius)

    objects = (
        db.query(MupiObject)
        .options(*mupi_load_options())
        .filter(
            MupiObject.active.is_(True),
            MupiObject.latitude.between(min_lat, max_lat),
            MupiObject.longitude.between(min_lng, max_lng),
        )
        .all()
    )

    visited = visited_ids(db, user.id)
    results = []

    for obj in objects:
        distance = haversine_m(latitude, longitude, obj.latitude, obj.longitude)

        if distance <= radius:
            results.append(serialize_summary(obj, obj.id in visited, distance))

    results.sort(key=lambda item: item["distance"])

    return results


@mupi_object_api_router.get("/search")
def search_mupi_objects(
    name: str = Query(..., min_length=1, max_length=100),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    objects = (
        db.query(MupiObject)
        .options(*mupi_load_options())
        .filter(
            MupiObject.active.is_(True),
            # autoescape: "%" e "_" digitados valem como texto, não curinga (FAL-17)
            MupiObject.name.icontains(name, autoescape=True),
        )
        .limit(50)
        .all()
    )

    visited = visited_ids(db, user.id)

    results = [
        serialize_summary(
            obj,
            obj.id in visited,
            haversine_m(latitude, longitude, obj.latitude, obj.longitude)
        )
        for obj in objects
    ]

    results.sort(key=lambda item: item["distance"])

    return results


# ---------- API do app: abrir o ponto (conteúdo completo + visita) ----------

class OpenMupiRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


@mupi_object_api_router.post("/{object_id}/open")
def open_mupi_object(
    object_id: int,
    data: OpenMupiRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Abre o ponto: confere a proximidade, registra a visita e entrega o conteúdo."""
    user_id = user.id

    mupi = get_mupi_in_range(db, object_id, data.latitude, data.longitude)

    try:
        new_visit, awarded = register_visit(db, user_id, mupi)
        db.commit()
    except IntegrityError:
        # Duas aberturas simultâneas: a outra registrou a visita primeiro
        db.rollback()
        new_visit, awarded = False, []

    awarded_data = [serialize_collected(item) for item in awarded]
    visits_total, _ = visit_counts(db, user_id)

    mupi = get_active_mupi(db, object_id, mupi_load_options())

    return {
        **serialize_content(mupi),
        "new_visit": new_visit,
        "visits_total": visits_total,
        "awarded": awarded_data,
    }


@mupi_object_api_router.get("/{object_id}/route")
def get_mupi_route(
    object_id: int,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db)
):
    mupi = get_active_mupi(db, object_id)

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
        headers={"Cache-Control": "private, max-age=86400"}
    )


@mupi_object_api_router.get("/{object_id}/image")
def get_mupi_object_image(
    object_id: int,
    db: Session = Depends(get_db)
):
    media = (
        db.query(MupiObjectMedia)
        .join(MupiObject, MupiObject.id == MupiObjectMedia.object_id)
        .filter(
            MupiObject.active.is_(True),
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
        headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/search")
def admin_search_mupi_objects(
    name: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db)
):
    objects = (
        db.query(MupiObject)
        .filter(MupiObject.name.icontains(name, autoescape=True))  # FAL-17
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
    # Só insígnias manuais são ligadas a um ponto; as de contagem valem para todos
    badges = (
        db.query(Badge)
        .filter(Badge.rule_type == BadgeRule.MANUAL)
        .order_by(Badge.name)
        .all()
    )

    themes = db.query(Theme).order_by(Theme.name).all()

    return templates.TemplateResponse(
        request=request,
        name="admin/mupi_object_form.html",
        context={
            "badges": badges,
            "themes": themes,
        }
    )


async def uploaded_images(request: Request) -> list[UploadFile]:
    """Imagens enviadas no campo "images", ignorando o campo vazio.

    Sem imagem escolhida, o navegador envia o campo de arquivo vazio, que
    chega como texto. Declarado como list[UploadFile], o FastAPI recusava o
    cadastro inteiro com erro 422 e o ponto não era salvo.
    """
    form = await request.form()

    return [
        item
        for item in form.getlist("images")
        if isinstance(item, StarletteUploadFile) and item.filename
    ]


@router.post("/mupi-objects")
def create_mupi_object(
    name: str = Form(..., max_length=150),
    description: str = Form(None),
    latitude: float = Form(..., ge=-90, le=90),
    longitude: float = Form(..., ge=-180, le=180),
    active: bool = Form(False),
    badge_ids: list[int] = Form([]),
    video_urls: str = Form(""),
    images: list[UploadFile] = Depends(uploaded_images),
    db: Session = Depends(get_db),
    theme_id: str = Form(""),
):

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

        if any(badge.rule_type != BadgeRule.MANUAL for badge in badges):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Só insígnias do tipo 'visitar este ponto' podem ser "
                    "ligadas a um ponto."
                )
            )

    media_items = []

    for image in images:
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
        theme_id=parsed_theme_id,
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
def badge_form(
    request: Request,
    db: Session = Depends(get_db)
):
    themes = db.query(Theme).order_by(Theme.name).all()

    return templates.TemplateResponse(
        request=request,
        name="admin/badge_form.html",
        context={
            "themes": themes,
            "rules": [
                (BadgeRule.MANUAL.value, "Visitar este ponto (ligada a um ponto MUPI)"),
                (BadgeRule.VISIT_COUNT.value, "Visitar N pontos quaisquer"),
                (BadgeRule.THEME_VISIT_COUNT.value, "Visitar N pontos de um tema"),
            ],
        }
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
        headers={"Cache-Control": "private, max-age=3600"}
    )