"""Configurações que o app precisa conhecer (exige login).

Hoje: a regra de distância para abrir um ponto (VIS-02). O app usa estes
valores para ligar o botão "Abrir" com a mesma regra do backend, sem repetir
o número no código do app. A decisão final continua sendo do backend (403).
"""
from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.service import proximity_service

router = APIRouter(
    tags=["App"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/app-settings")
def get_app_settings():
    return {
        # Distância máxima até o ponto, em metros
        "visit_max_distance_m": proximity_service.max_distance(),
        # Até quanto da precisão do GPS é somado à distância máxima
        "visit_gps_tolerance_m": proximity_service.gps_tolerance(),
    }
