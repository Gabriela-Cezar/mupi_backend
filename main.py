from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.controller.email_controller import router as email_router
from app.controller.auth_controller import router as auth_router
from app.controller.user_controller import router as user_router
from app.controller.admin_theme_controller import router as admin_theme_router
from app.controller.mupi_object_controller import (
    router as mupi_object_router,
    mupi_object_api_router
)

app = FastAPI(title="MUPI API")

app.include_router(user_router)

BASE_DIR = Path(__file__).resolve().parent

app.include_router(admin_theme_router)

app.mount(
    "/admin-static",
    StaticFiles(directory=BASE_DIR / "app" / "templates" / "admin"),
    name="admin-static"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(email_router)
app.include_router(auth_router)
app.include_router(mupi_object_router)
app.include_router(mupi_object_api_router)