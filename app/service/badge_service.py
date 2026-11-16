from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.mupi_object_theme import MupiObjectTheme
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit


def visit_counts(db: Session, user_id: int) -> tuple[int, dict[int, int]]:
    """Devolve (total de MUPIs visitados, visitados por tema).

    Conta todas as visitas registradas, inclusive a pontos hoje desativados:
    a visita aconteceu, e desativar um ponto não pode fazer o progresso das
    insígnias do usuário diminuir (FAL-12 / INS-05).

    Um ponto com vários temas conta uma vez para cada tema (PT-03).
    """
    total = (
        db.query(func.count(UserVisit.object_id))
        .filter(UserVisit.user_id == user_id)
        .scalar()
    )

    rows = (
        db.query(MupiObjectTheme.theme_id, func.count(UserVisit.object_id))
        .select_from(UserVisit)
        .join(MupiObjectTheme, MupiObjectTheme.object_id == UserVisit.object_id)
        .filter(UserVisit.user_id == user_id)
        .group_by(MupiObjectTheme.theme_id)
        .all()
    )

    return total, dict(rows)


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
    mupi: MupiObject,
    latitude: float | None = None,
    longitude: float | None = None,
    accuracy: float | None = None,
) -> tuple[bool, list[UserBadge]]:
    """Registra a visita (uma por usuário e MUPI) e avalia as condições.

    Guarda onde o usuário estava e a precisão do GPS (VIS-03). Devolve
    (visita_nova, insígnias_conquistadas). Não faz commit.
    """
    if db.get(UserVisit, (user_id, mupi.id)) is not None:
        return False, []

    db.add(UserVisit(
        user_id=user_id,
        object_id=mupi.id,
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
    ))

    db.flush()

    return True, award_visit_badges(db, user_id, mupi.id)