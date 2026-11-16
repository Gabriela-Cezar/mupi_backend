import logging

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
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy.orm import Session

from app.controller import mupi_object_form as form
from app.controller.serializers import (
    mupi_load_options,
    serialize_collected,
    serialize_content,
    serialize_summary,
)
from app.core.admin_auth import require_admin_with_csrf
from app.core.config import OPENROUTESERVICE_API_KEY
from app.core.dependencies import get_current_user
from app.core.file_types import sniff_image_mime
from app.core.templates import templates
from app.database.database import get_db
from app.model.badge import Badge, BadgeRule
from app.model.theme import Theme
from app.model.mupi_object import MupiObject
from app.model.mupi_object_badge import MupiObjectBadge  # noqa: F401  (registra a tabela de associação)
from app.model.user import User
from app.model.user_visit import UserVisit
from app.service import storage_service
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


def store_file(
    db: Session, prefix: str, name: str, data: bytes, content_type: str
) -> str:
    """Envia o arquivo ao S3 e devolve a chave, com erro claro para o painel.

    Se o envio falhar, desfaz o que estava pendente no banco.
    """
    key = storage_service.build_key(prefix, name, content_type)

    try:
        return storage_service.save(key, data, content_type)
    except storage_service.StorageNotConfigured:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Armazenamento de arquivos não configurado (S3_BUCKET)."
        )
    except storage_service.StorageError:
        db.rollback()
        logger.exception("Erro ao enviar arquivo para o S3")
        raise HTTPException(
            status_code=502,
            detail="Não foi possível salvar o arquivo. Tente novamente."
        )


def commit_or_delete_file(db: Session, key: str | None) -> None:
    """Grava no banco; se falhar, apaga o arquivo recém-enviado ao S3."""
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage_service.delete_quietly(key)
        raise


# ---------- API do app: resumo (mapa, próximos, busca) ----------

def visited_ids(db: Session, user_id: int) -> set[int]:
    return {
        object_id
        for (object_id,) in db.query(UserVisit.object_id)
        .filter(UserVisit.user_id == user_id)
    }


def visible_on_map():
    """Pontos ativos que existem individualmente (PT-09, PT-10, PT-11)."""
    return (
        MupiObject.active.is_(True),
        MupiObject.standalone.is_(True),
    )


@mupi_object_api_router.get("")
def get_mupi_objects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    objects = (
        db.query(MupiObject)
        .options(*mupi_load_options())
        .filter(*visible_on_map())
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
            *visible_on_map(),
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
            *visible_on_map(),
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

    api_key = OPENROUTESERVICE_API_KEY

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
            "latitude": obj.latitude,
            "longitude": obj.longitude,
            "active": obj.active,
            "standalone": obj.standalone,
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


async def uploaded_photo(request: Request) -> UploadFile | None:
    """Foto enviada no campo "photo", ignorando o campo vazio.

    Sem arquivo escolhido, o navegador envia o campo vazio, que chega como
    texto. Declarado como UploadFile, o FastAPI recusaria o cadastro inteiro
    com erro 422 e o ponto não seria salvo.
    """
    form = await request.form()
    item = form.get("photo")

    if isinstance(item, StarletteUploadFile) and item.filename:
        return item

    return None


@router.post("/mupi-objects")
def create_mupi_object(
    name: str = Form(..., max_length=150),
    latitude: float = Form(..., ge=-90, le=90),
    longitude: float = Form(..., ge=-180, le=180),
    active: bool = Form(False),
    # Marcado = o ponto só aparece dentro de rotas (PT-09)
    route_only: bool = Form(False),
    theme_ids: list[int] = Form([]),
    badge_ids: list[int] = Form([]),
    section_title: list[str] = Form([]),
    section_body: list[str] = Form([]),
    video_url: list[str] = Form([]),
    video_title: list[str] = Form([]),
    address: str = Form(""),
    opening_hours: str = Form(""),
    accessibility: str = Form(""),
    photo: UploadFile | None = Depends(uploaded_photo),
    db: Session = Depends(get_db),
):
    name = name.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Informe o nome do ponto.")

    # Valida tudo antes de gravar qualquer coisa
    themes = form.load_themes(db, theme_ids)
    badges = form.load_point_badges(db, badge_ids)
    sections = form.build_sections(section_title, section_body)
    videos = form.build_videos(video_url, video_title)
    photo_file = read_image(photo) if photo is not None else None

    mupi_object = MupiObject(
        name=name,
        latitude=latitude,
        longitude=longitude,
        active=active,
        standalone=not route_only,
        address=form.optional_text(address, "Endereço", form.MAX_ADDRESS),
        opening_hours=form.optional_text(
            opening_hours, "Horário de funcionamento", form.MAX_LONG_TEXT
        ),
        accessibility=form.optional_text(
            accessibility, "Acessibilidade", form.MAX_LONG_TEXT
        ),
        themes=themes,
        badges=badges,
        sections=sections,
        videos=videos,
    )

    db.add(mupi_object)
    # Gera o id do ponto, usado no caminho da foto no S3
    db.flush()

    if photo_file is not None:
        photo_data, photo_mime = photo_file
        mupi_object.photo_key = store_file(
            db, f"points/{mupi_object.id}", "photo", photo_data, photo_mime
        )

    commit_or_delete_file(db, mupi_object.photo_key)

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

    image_file = read_image(image) if image and image.filename else None

    badge = Badge(
        name=name,
        description=description,
        rule_type=rule,
        required_count=count,
        theme_id=theme
    )

    db.add(badge)

    try:
        # Gera o id da insígnia, usado no caminho da imagem no S3
        db.flush()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail="Já existe uma insígnia com esse nome."
        )

    if image_file is not None:
        image_data, image_mime = image_file
        badge.image_key = store_file(
            db, f"badges/{badge.id}", "image", image_data, image_mime
        )

    commit_or_delete_file(db, badge.image_key)

    db.refresh(badge)

    return {
        "message": "Insígnia cadastrada com sucesso!",
        "id": badge.id
    }
    
