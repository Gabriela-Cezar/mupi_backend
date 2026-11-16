from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.mupi_object_theme import MupiObjectTheme
from app.model.user_badge import UserBadge
from app.model.user_route_completion import UserRouteCompletion
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


def award_badges(
    db: Session,
    user_id: int,
    object_id: int | None = None,
) -> list[UserBadge]:
    """Concede as insígnias ativas cujas condições o usuário já cumpre.

    - visita a ponto: o usuário já visitou o ponto da insígnia (INS-02),
      mesmo que a visita seja anterior à insígnia;
    - quantidade geral e por tema: pela contagem de visitas (INS-03, INS-05);
    - conclusão de rota: o usuário já concluiu a rota (INS-04), mesmo antes
      de a insígnia existir. Uma vez só, mesmo refazendo a rota.

    Chamada a cada visita nova ([object_id] = o ponto visitado agora) e ao
    carregar o perfil, sem ponto, para a avaliação retroativa (INS-06).
    Insígnias desativadas não são concedidas. Não faz commit.
    """
    collected_ids = (
        db.query(UserBadge.badge_id)
        .filter(UserBadge.user_id == user_id)
    )

    pending = (
        db.query(Badge)
        .filter(Badge.active.is_(True), Badge.id.notin_(collected_ids))
        .order_by(Badge.id)
        .all()
    )

    if not pending:
        return []

    total, by_theme = visit_counts(db, user_id)

    visited = {
        visited_id for (visited_id,) in
        db.query(UserVisit.object_id).filter(UserVisit.user_id == user_id)
    }

    completed_routes = {
        route_id for (route_id,) in
        db.query(UserRouteCompletion.route_id)
        .filter(UserRouteCompletion.user_id == user_id)
        .distinct()
    }

    awarded = []

    for badge in pending:
        route_id = None

        if badge.rule_type == BadgeRule.ROUTE_COMPLETION:
            if badge.route_id not in completed_routes:
                continue
            # Conquistada na rota; não houve um ponto
            route_id, where = badge.route_id, None
        elif badge.rule_type == BadgeRule.POINT_VISIT:
            if badge.object_id not in visited:
                continue
            # Conquistada no próprio ponto da insígnia
            where = badge.object_id
        elif progress_of(badge, total, by_theme) >= badge.required_count:
            # Na visita que completou a contagem; na avaliação retroativa,
            # não houve um ponto
            where = object_id
        else:
            continue

        item = UserBadge(
            user_id=user_id,
            badge_id=badge.id,
            collected_at_object_id=where,
            collected_at_route_id=route_id,
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

    Reabrir um ponto já visitado também avalia as insígnias: uma insígnia
    criada depois da visita é entregue na próxima abertura (INS-02, INS-06).
    """
    if db.get(UserVisit, (user_id, mupi.id)) is not None:
        return False, award_badges(db, user_id, mupi.id)

    db.add(UserVisit(
        user_id=user_id,
        object_id=mupi.id,
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
    ))

    db.flush()

    return True, award_badges(db, user_id, mupi.id)