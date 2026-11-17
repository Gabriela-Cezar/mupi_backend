from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import API_DOCS, CORS_ALLOWED_ORIGIN_REGEX, CORS_ALLOWED_ORIGINS
from app.core.cors import add_cors, parse_origins
from app.controller.email_controller import router as email_router
from app.controller.auth_controller import router as auth_router
from app.controller.user_controller import router as user_router
from app.controller.admin_auth_controller import router as admin_auth_router
from app.controller.admin_theme_controller import router as admin_theme_router
from app.controller.admin_mupi_object_controller import router as admin_mupi_object_router
from app.controller.admin_badge_controller import router as admin_badge_router
from app.controller.admin_route_controller import router as admin_route_router
from app.controller.admin_route_point_content_controller import router as admin_route_point_content_router
from app.controller.route_controller import router as route_router
from app.controller.active_route_controller import (
    router as active_route_router,
    start_router as route_start_router,
)
from app.controller.local_files_controller import router as local_files_router
from app.controller.app_settings_controller import router as app_settings_router
from app.controller.mupi_object_controller import (
    router as mupi_object_router,
    mupi_object_api_router
)



def docs_urls(enabled: bool) -> dict:
    """Documentação automática só quando ligada (API_DOCS, INF-09)."""
    if enabled:
        return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}

    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


app = FastAPI(title="MUPI API", **docs_urls(API_DOCS))

app.include_router(user_router)

BASE_DIR = Path(__file__).resolve().parent

app.include_router(admin_auth_router)
app.include_router(admin_theme_router)
app.include_router(admin_mupi_object_router)
app.include_router(admin_badge_router)
app.include_router(admin_route_router)
app.include_router(admin_route_point_content_router)

app.mount(
    "/admin-static",
    StaticFiles(directory=BASE_DIR / "app" / "templates" / "admin"),
    name="admin-static"
)


# Só os sites configurados no .env podem chamar a API pelo navegador (FAL-09)
add_cors(
    app,
    origins=parse_origins(CORS_ALLOWED_ORIGINS),
    origin_regex=CORS_ALLOWED_ORIGIN_REGEX,
)


app.include_router(email_router)
app.include_router(auth_router)
app.include_router(mupi_object_router)
app.include_router(mupi_object_api_router)
app.include_router(app_settings_router)
app.include_router(route_router)
app.include_router(route_start_router)
app.include_router(active_route_router)
# Arquivos da pasta local (LOCAL_STORAGE_DIR, só desenvolvimento)
app.include_router(local_files_router)