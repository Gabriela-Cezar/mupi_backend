"""Formulário de rota do painel (ADM-07): leitura, validação e gravação.

1. read_route_form: o que o administrador digitou, sem validar;
2. validate_route: confere tudo e devolve os valores prontos, ou FormError;
3. apply_route: grava os valores na rota (o trajeto é calculado à parte).

activation_problems diz o que falta para a rota poder ser ativada.
"""
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.controller.mupi_object_form import FormError, load_themes, optional_text
from app.model.mupi_object import MupiObject
from app.model.route import AgeRating, Route, RouteDifficulty, RoutePoint
from app.model.theme import Theme
from app.service.route_path_service import MAX_ROUTE_POINTS

MAX_NAME = 150
MAX_DESCRIPTION = 5_000
MAX_MINUTES = 24 * 60

DIFFICULTY_LABELS = {
    RouteDifficulty.EASY: "Fácil",
    RouteDifficulty.MEDIUM: "Média",
    RouteDifficulty.HARD: "Difícil",
}

AGE_RATING_LABELS = {
    AgeRating.FREE: "Livre",
    AgeRating.AGE_10: "10 anos",
    AgeRating.AGE_12: "12 anos",
    AgeRating.AGE_14: "14 anos",
    AgeRating.AGE_16: "16 anos",
    AgeRating.AGE_18: "18 anos",
}


# ---------- 1. Leitura (sem validar) ----------

@dataclass
class RouteDraft:
    name: str = ""
    description: str = ""
    difficulty: str = RouteDifficulty.EASY.value
    age_rating: str = AgeRating.FREE.value
    theme_ids: list[str] = field(default_factory=list)
    # Pontos na ordem da rota
    point_ids: list[str] = field(default_factory=list)
    estimated_minutes: str = ""
    active: bool = False
    remove_cover: bool = False
    cover_key: str | None = None


def _text(form: FormData, name: str) -> str:
    value = form.get(name)
    return value if isinstance(value, str) else ""


def _texts(form: FormData, name: str) -> list[str]:
    return [v for v in form.getlist(name) if isinstance(v, str)]


def _checked(form: FormData, name: str) -> bool:
    return _text(form, name).lower() in ("true", "on", "1")


def read_route_form(form: FormData) -> RouteDraft:
    return RouteDraft(
        name=_text(form, "name"),
        description=_text(form, "description"),
        difficulty=_text(form, "difficulty"),
        age_rating=_text(form, "age_rating"),
        theme_ids=_texts(form, "theme_ids"),
        point_ids=_texts(form, "point_ids"),
        estimated_minutes=_text(form, "estimated_minutes"),
        active=_checked(form, "active"),
        remove_cover=_checked(form, "remove_cover"),
    )


def draft_from_route(route: Route) -> RouteDraft:
    return RouteDraft(
        name=route.name,
        description=route.description or "",
        difficulty=route.difficulty.value,
        age_rating=route.age_rating.value,
        theme_ids=[str(t.id) for t in route.themes],
        point_ids=[str(i) for i in route.point_ids],
        estimated_minutes=str(route.estimated_minutes or ""),
        active=route.active,
        cover_key=route.cover_key,
    )


# ---------- 2. Validação ----------

@dataclass
class RouteData:
    name: str
    description: str | None
    difficulty: RouteDifficulty
    age_rating: AgeRating
    themes: list[Theme]
    points: list[MupiObject]
    estimated_minutes: int | None
    active: bool


def _points(db: Session, draft: RouteDraft, route: Route | None) -> list[MupiObject]:
    ids: list[int] = []

    for value in draft.point_ids:
        try:
            ids.append(int(value))
        except ValueError:
            raise FormError("Valor inválido para ponto.")

    if len(ids) < 2:
        raise FormError("A rota precisa de pelo menos 2 pontos.")

    if len(ids) > MAX_ROUTE_POINTS:
        raise FormError(f"A rota pode ter no máximo {MAX_ROUTE_POINTS} pontos.")

    if len(set(ids)) != len(ids):
        raise FormError("O mesmo ponto não pode aparecer duas vezes na rota.")

    found = {p.id: p for p in db.query(MupiObject).filter(MupiObject.id.in_(ids))}

    if len(found) != len(ids):
        raise FormError("Ponto não encontrado.")

    # Só pontos ativos podem entrar; os que já estavam na rota e foram
    # desativados podem ficar (a rota fica desativada até ser corrigida)
    already = set(route.point_ids) if route is not None else set()
    new_inactive = [found[i].name for i in ids if not found[i].active and i not in already]

    if new_inactive:
        raise FormError(
            "Ponto desativado não pode entrar na rota: " + ", ".join(new_inactive) + "."
        )

    return [found[i] for i in ids]


def validate_route(db: Session, draft: RouteDraft, route: Route | None = None) -> RouteData:
    name = draft.name.strip()

    if not name:
        raise FormError("Informe o nome da rota.")

    if len(name) > MAX_NAME:
        raise FormError(f"Nome: máximo de {MAX_NAME} caracteres.")

    duplicate = db.query(Route.id).filter(func.lower(Route.name) == name.lower())
    if route is not None:
        duplicate = duplicate.filter(Route.id != route.id)
    if duplicate.first():
        raise FormError("Já existe uma rota com esse nome.")

    try:
        difficulty = RouteDifficulty(draft.difficulty)
    except ValueError:
        raise FormError("Escolha a dificuldade.")

    try:
        age_rating = AgeRating(draft.age_rating)
    except ValueError:
        raise FormError("Escolha a classificação indicativa.")

    minutes = None
    if draft.estimated_minutes.strip():
        try:
            minutes = int(draft.estimated_minutes.strip())
        except ValueError:
            minutes = 0
        if not 1 <= minutes <= MAX_MINUTES:
            raise FormError(f"Tempo estimado: um número de minutos entre 1 e {MAX_MINUTES}.")

    return RouteData(
        name=name,
        description=optional_text(draft.description, "Descrição", MAX_DESCRIPTION),
        difficulty=difficulty,
        age_rating=age_rating,
        themes=load_themes(db, draft.theme_ids),
        points=_points(db, draft, route),
        estimated_minutes=minutes,
        active=draft.active,
    )


def activation_problems(route: Route) -> list[str]:
    """O que falta para a rota poder ficar ativa no app. Vazio = pode."""
    problems = []

    if not route.cover_key:
        problems.append("Envie a imagem de capa.")

    if len(route.points) < 2:
        problems.append("A rota precisa de pelo menos 2 pontos.")

    inactive = [rp.mupi_object.name for rp in route.points if not rp.mupi_object.active]
    if inactive:
        problems.append("Ponto desativado na rota: " + ", ".join(inactive) + ".")

    if not route.has_path:
        problems.append("A rota está sem trajeto: recalcule o trajeto.")

    return problems


# ---------- 3. Gravação ----------

def apply_route(db: Session, route: Route, data: RouteData) -> bool:
    """Grava os dados. Devolve True se os pontos ou a ordem mudaram (o
    trajeto precisa ser recalculado). Não mexe em `active`: a ativação é
    conferida depois do trajeto (ver activation_problems)."""
    route.name = data.name
    route.description = data.description
    route.difficulty = data.difficulty
    route.age_rating = data.age_rating
    route.themes = data.themes
    route.estimated_minutes = data.estimated_minutes

    new_ids = [p.id for p in data.points]
    changed = new_ids != route.point_ids

    if changed:
        # Troca a lista inteira. A remoção é gravada antes: o SQLAlchemy
        # grava inserções antes de remoções, e as linhas novas esbarrariam
        # nas chaves únicas (rota, posição) e (rota, ponto) das antigas
        route.points.clear()
        db.flush()
        route.points.extend(
            RoutePoint(object_id=p.id, position=i, mupi_object=p)
            for i, p in enumerate(data.points)
        )

    return changed
