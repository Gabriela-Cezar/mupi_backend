import math

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import config
from app.model.mupi_object import MupiObject

EARTH_RADIUS_M = 6_371_000


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


def get_active_mupi(db: Session, object_id: int, options=()) -> MupiObject:
    """Ponto ativo que existe individualmente (PT-09).

    Um ponto que só existe dentro de rotas não pode ser aberto nem ter o
    "Como chegar" fora de uma rota ativa. Enquanto as rotas não existem
    (Etapa 5), ele responde como não encontrado.
    """
    mupi = (
        db.query(MupiObject)
        .options(*options)
        .filter(
            MupiObject.id == object_id,
            MupiObject.active.is_(True),
            MupiObject.standalone.is_(True),
        )
        .first()
    )

    if mupi is None:
        raise HTTPException(
            status_code=404,
            detail="MUPI não encontrado."
        )

    return mupi


def max_distance() -> float:
    """Distância máxima para abrir um ponto, em metros (VIS-02, no .env)."""
    return config.VISIT_MAX_DISTANCE_M


def gps_tolerance() -> float:
    """Quanto da precisão do GPS pode ser somado à distância máxima."""
    return config.VISIT_GPS_TOLERANCE_M


def allowed_distance(accuracy: float | None) -> float:
    """Distância aceita para quem informou esta precisão do GPS (VIS-02).

    Soma à distância máxima a precisão do celular, até a tolerância: um GPS
    com erro de 10 m não impede quem está realmente no local, e um GPS ruim
    (erro de 200 m) não libera o ponto de longe.
    """
    tolerance = min(max(accuracy or 0, 0), gps_tolerance())
    return max_distance() + tolerance


def _meters(value: float) -> str:
    return f"{value:.0f}"


def get_mupi_in_range(
    db: Session,
    object_id: int,
    latitude: float,
    longitude: float,
    accuracy: float | None = None,
    options=()
) -> MupiObject:
    """Ponto ativo, se o usuário estiver perto dele; senão 404 ou 403 (VIS-01)."""
    mupi = get_active_mupi(db, object_id, options)

    distance = haversine_m(latitude, longitude, mupi.latitude, mupi.longitude)

    if distance > allowed_distance(accuracy):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Aproxime-se do MUPI (você está a {_meters(distance)} m; "
                f"o limite é {_meters(max_distance())} m)."
            )
        )

    return mupi
