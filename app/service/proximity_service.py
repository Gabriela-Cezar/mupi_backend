import math

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.model.mupi_object import MupiObject

EARTH_RADIUS_M = 6_371_000

# Distância máxima para abrir um ponto e registrar a visita.
# Será configurável e ajustada no beta (VIS-02).
PROXIMITY_RADIUS_M = 50


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
    mupi = (
        db.query(MupiObject)
        .options(*options)
        .filter(
            MupiObject.id == object_id,
            MupiObject.active.is_(True)
        )
        .first()
    )

    if mupi is None:
        raise HTTPException(
            status_code=404,
            detail="MUPI não encontrado."
        )

    return mupi


def get_mupi_in_range(
    db: Session,
    object_id: int,
    latitude: float,
    longitude: float,
    options=()
) -> MupiObject:
    mupi = get_active_mupi(db, object_id, options)

    distance = haversine_m(latitude, longitude, mupi.latitude, mupi.longitude)

    if distance > PROXIMITY_RADIUS_M:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Aproxime-se do MUPI (você está a {round(distance)} m; "
                f"o limite é {PROXIMITY_RADIUS_M} m)."
            )
        )

    return mupi
