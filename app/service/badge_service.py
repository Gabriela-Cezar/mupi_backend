from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit


def visit_counts(db: Session, user_id: int) -> tuple[int, dict[int, int]]:
    """Devolve (total de MUPIs visitados, visitados por tema)."""
    rows = (
        db.query(MupiObject.theme_id, func.count(UserVisit.object_id))
        .select_from(UserVisit)
        .join(MupiObject, MupiObject.id == UserVisit.object_id)
        .filter(
            UserVisit.user_id == user_id,
            MupiObject.active.is_(True)
        )
        .group_by(MupiObject.theme_id)
        .all()
    )

    total = sum(count for _, count in rows)
    by_theme = {
        theme_id: count for theme_id, count in rows if theme_id is not None
    }

    return total, by_theme


def progress_of(badge: Badge, total: int, by_theme: dict[int, int]) -> int:
    if badge.rule_type == BadgeRule.VISIT_COUNT:
        return total

    if badge.rule_type == BadgeRule.THEME_VISIT_COUNT:
        return by_theme.get(badge.theme_id, 0)

    return 0


def award_visit_badges(
    db: Session,
    user_id: int,
    object_id: int
) -> list[UserBadge]:
    """Concede as insígnias condicionais cujas condições foram cumpridas.

    Não faz commit: quem chama decide quando confirmar.
    """
    collected_ids = (
        db.query(UserBadge.badge_id)
        .filter(UserBadge.user_id == user_id)
    )

    pending = (
        db.query(Badge)
        .filter(
            Badge.rule_type != BadgeRule.MANUAL,
            Badge.id.notin_(collected_ids)
        )
        .all()
    )

    if not pending:
        return []

    total, by_theme = visit_counts(db, user_id)

    awarded = []

    for badge in pending:
        if progress_of(badge, total, by_theme) >= badge.required_count:
            item = UserBadge(
                user_id=user_id,
                badge_id=badge.id,
                collected_at_object_id=object_id
            )

            db.add(item)
            awarded.append(item)

    if awarded:
        db.flush()

    return awarded


def register_visit(
    db: Session,
    user_id: int,
    mupi: MupiObject
) -> tuple[bool, list[UserBadge]]:
    """Registra a visita (uma por usuário e MUPI) e avalia as condições.

    Devolve (visita_nova, insígnias_conquistadas). Não faz commit.
    """
    if db.get(UserVisit, (user_id, mupi.id)) is not None:
        return False, []

    db.add(UserVisit(user_id=user_id, object_id=mupi.id))

    db.flush()

    return True, award_visit_badges(db, user_id, mupi.id)