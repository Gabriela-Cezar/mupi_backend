from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.controller.serializers import serialize_badge_full, serialize_collected
from app.core.dependencies import get_current_user
from app.database.database import get_db
from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.mupi_object_badge import MupiObjectBadge
from app.model.user import User
from app.model.user_badge import UserBadge
from app.service.badge_service import (
    progress_of,
    register_visit,
    visit_counts,
)
from app.service.proximity_service import get_mupi_in_range

router = APIRouter(
    prefix="/users",
    tags=["Usuários"]
)


class CheckInRequest(BaseModel):
    object_id: int
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CollectBadgeRequest(CheckInRequest):
    badge_id: int


@router.get("/me")
def get_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    collected = (
        db.query(UserBadge)
        .options(
            selectinload(UserBadge.badge).selectinload(Badge.theme),
            selectinload(UserBadge.mupi_object),
        )
        .filter(UserBadge.user_id == user.id)
        .order_by(UserBadge.collected_at.desc())
        .all()
    )

    visits_total, by_theme = visit_counts(db, user.id)

    collected_ids = (
        db.query(UserBadge.badge_id)
        .filter(UserBadge.user_id == user.id)
    )

    pending = (
        db.query(Badge)
        .options(selectinload(Badge.theme))
        .filter(
            Badge.rule_type != BadgeRule.MANUAL,
            Badge.id.notin_(collected_ids)
        )
        .order_by(Badge.required_count)
        .all()
    )

    in_progress = [
        {
            **serialize_badge_full(badge),
            "progress": min(
                progress_of(badge, visits_total, by_theme),
                badge.required_count
            ),
        }
        for badge in pending
    ]

    manual_total = (
        db.query(func.count(distinct(MupiObjectBadge.badge_id)))
        .select_from(MupiObjectBadge)
        .join(MupiObject, MupiObject.id == MupiObjectBadge.object_id)
        .join(Badge, Badge.id == MupiObjectBadge.badge_id)
        .filter(
            MupiObject.active.is_(True),
            Badge.rule_type == BadgeRule.MANUAL
        )
        .scalar()
    ) or 0

    conditional_total = (
        db.query(func.count(Badge.id))
        .filter(Badge.rule_type != BadgeRule.MANUAL)
        .scalar()
    ) or 0

    return {
        "id": user.id,
        "email": user.email,
        "created_at": user.created_at.isoformat(),
        "visits_total": visits_total,
        "badges_collected": len(collected),
        "badges_total": max(manual_total + conditional_total, len(collected)),
        "badges": [serialize_collected(item) for item in collected],
        "in_progress": in_progress,
    }


@router.post("/me/visits")
def check_in(
    data: CheckInRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = user.id

    mupi = get_mupi_in_range(db, data.object_id, data.latitude, data.longitude)

    try:
        new_visit, awarded = register_visit(db, user_id, mupi)
        db.commit()
    except IntegrityError:
        db.rollback()
        new_visit, awarded = False, []

    visits_total, _ = visit_counts(db, user_id)

    return {
        "new_visit": new_visit,
        "visits_total": visits_total,
        "awarded": [serialize_collected(item) for item in awarded],
    }


@router.post("/me/badges")
def collect_badge(
    data: CollectBadgeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = user.id

    mupi = get_mupi_in_range(db, data.object_id, data.latitude, data.longitude)

    badge = (
        db.query(Badge)
        .join(MupiObjectBadge, MupiObjectBadge.badge_id == Badge.id)
        .filter(
            MupiObjectBadge.object_id == mupi.id,
            Badge.id == data.badge_id,
            Badge.rule_type == BadgeRule.MANUAL
        )
        .first()
    )

    if badge is None:
        raise HTTPException(
            status_code=404,
            detail="Esta insígnia não está disponível neste MUPI."
        )

    badge_id = badge.id
    already = db.get(UserBadge, (user_id, badge_id)) is not None
    awarded = []

    try:
        if not already:
            db.add(UserBadge(
                user_id=user_id,
                badge_id=badge_id,
                collected_at_object_id=mupi.id
            ))
            db.flush()

        _, awarded = register_visit(db, user_id, mupi)

        db.commit()
    except IntegrityError:
        db.rollback()
        awarded = []
        already = True

    item = db.get(UserBadge, (user_id, badge_id))

    if item is None:
        raise HTTPException(
            status_code=409,
            detail="Não foi possível concluir a coleta. Tente novamente."
        )

    return {
        "new": not already,
        "badge": serialize_collected(item),
        "awarded": [serialize_collected(a) for a in awarded],
    }