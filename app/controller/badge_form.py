"""Formulário de insígnia do painel (ADM-06): leitura, validação e gravação.

1. read_badge_form: o que o administrador digitou, sem validar (para mostrar
   o formulário de novo com os mesmos valores, em caso de erro);
2. validate_badge: confere tudo e devolve os valores prontos, ou FormError;
3. apply_badge: grava os valores na insígnia.

O formulário muda conforme o tipo (corrige FAL-03): visita a ponto pede o
ponto; quantidade geral, o N; quantidade por tema, o tema e o N; conclusão
de rota, a rota (uma insígnia de conclusão por rota).
"""
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.controller.mupi_object_form import FormError
from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.route import Route
from app.model.theme import Theme

MAX_NAME = 100
MAX_DESCRIPTION = 2_000
MAX_COUNT = 1_000

RULE_LABELS = {
    BadgeRule.POINT_VISIT: "Visita a ponto",
    BadgeRule.VISIT_COUNT: "Quantidade geral",
    BadgeRule.THEME_VISIT_COUNT: "Quantidade por tema",
    BadgeRule.ROUTE_COMPLETION: "Conclusão de rota",
}


def condition_of(badge: Badge) -> str:
    """Condição resumida para a lista (ex.: "Visitar 5 pontos de Arte Deco")."""
    if badge.rule_type == BadgeRule.POINT_VISIT:
        name = badge.mupi_object.name if badge.mupi_object else "?"
        return f"Visitar {name}"

    if badge.rule_type == BadgeRule.ROUTE_COMPLETION:
        name = badge.route.name if badge.route else "?"
        return f"Concluir a rota {name}"

    count = badge.required_count
    points = "1 ponto" if count == 1 else f"{count} pontos"

    if badge.rule_type == BadgeRule.THEME_VISIT_COUNT:
        theme = badge.theme.name if badge.theme else "?"
        return f"Visitar {points} de {theme}"

    return f"Visitar {points}"


# ---------- 1. Leitura (sem validar) ----------

@dataclass
class BadgeDraft:
    """O que o administrador digitou, no formato que o template usa."""
    name: str = ""
    description: str = ""
    rule_type: str = BadgeRule.POINT_VISIT.value
    object_id: str = ""
    route_id: str = ""
    theme_id: str = ""
    required_count: str = ""
    active: bool = True
    remove_image: bool = False
    # Na edição, a imagem atual continua aparecendo
    image_key: str | None = None


def _text(form: FormData, name: str) -> str:
    value = form.get(name)
    return value if isinstance(value, str) else ""


def read_badge_form(form: FormData) -> BadgeDraft:
    return BadgeDraft(
        name=_text(form, "name"),
        description=_text(form, "description"),
        rule_type=_text(form, "rule_type"),
        object_id=_text(form, "object_id"),
        route_id=_text(form, "route_id"),
        theme_id=_text(form, "theme_id"),
        required_count=_text(form, "required_count"),
        active=_text(form, "active").lower() in ("true", "on", "1"),
        remove_image=_text(form, "remove_image").lower() in ("true", "on", "1"),
    )


def draft_from_badge(badge: Badge) -> BadgeDraft:
    """A insígnia salva, no formato do formulário (tela de edição)."""
    return BadgeDraft(
        name=badge.name,
        description=badge.description or "",
        rule_type=badge.rule_type.value,
        object_id=str(badge.object_id or ""),
        route_id=str(badge.route_id or ""),
        theme_id=str(badge.theme_id or ""),
        required_count=str(badge.required_count or ""),
        active=badge.active,
        image_key=badge.image_key,
    )


# ---------- 2. Validação ----------

@dataclass
class BadgeData:
    name: str
    description: str | None
    rule_type: BadgeRule
    object_id: int | None
    theme_id: int | None
    required_count: int | None
    active: bool
    route_id: int | None = None


def _int(value: str) -> int | None:
    try:
        return int(value.strip())
    except (AttributeError, ValueError):
        return None


def _route_rule(db: Session, draft: BadgeDraft, badge: Badge | None) -> int:
    route_id = _int(draft.route_id)

    if route_id is None:
        raise FormError("Selecione a rota da insígnia.")

    if db.get(Route, route_id) is None:
        raise FormError("Rota não encontrada.")

    # Uma rota tem no máximo uma insígnia de conclusão (INS-04)
    other = db.query(Badge).filter(Badge.route_id == route_id)
    if badge is not None:
        other = other.filter(Badge.id != badge.id)
    other = other.first()

    if other is not None:
        raise FormError(f"Esta rota já tem uma insígnia de conclusão: {other.name}.")

    return route_id


def _rule(db: Session, draft: BadgeDraft, badge: Badge | None = None):
    """(tipo, ponto, tema, quantidade, rota) conferidos."""
    try:
        rule = BadgeRule(draft.rule_type)
    except ValueError:
        raise FormError("Escolha como a insígnia é conquistada.")

    if rule == BadgeRule.ROUTE_COMPLETION:
        return rule, None, None, None, _route_rule(db, draft, badge)

    if rule == BadgeRule.POINT_VISIT:
        point_id = _int(draft.object_id)

        if point_id is None:
            raise FormError("Selecione o ponto da insígnia.")

        if db.get(MupiObject, point_id) is None:
            raise FormError("Ponto não encontrado.")

        return rule, point_id, None, None, None

    count = _int(draft.required_count)

    if count is None or count < 1:
        raise FormError("Informe a quantidade de pontos a visitar (um número inteiro, 1 ou mais).")

    if count > MAX_COUNT:
        raise FormError(f"Quantidade: no máximo {MAX_COUNT}.")

    if rule == BadgeRule.VISIT_COUNT:
        return rule, None, None, count, None

    theme_id = _int(draft.theme_id)

    if theme_id is None:
        raise FormError("Selecione o tema.")

    if db.get(Theme, theme_id) is None:
        raise FormError("Tema não encontrado.")

    return rule, None, theme_id, count, None


def validate_badge(
    db: Session,
    draft: BadgeDraft,
    badge: Badge | None = None,
    rule_locked: bool = False,
) -> BadgeData:
    """Confere o formulário. Com [rule_locked] (insígnia já conquistada), a
    regra salva é mantida e o que veio no formulário para ela é ignorado."""
    name = draft.name.strip()
    description = draft.description.replace("\r\n", "\n").strip() or None

    if not name:
        raise FormError("Informe o nome da insígnia.")

    if len(name) > MAX_NAME:
        raise FormError(f"Nome: máximo de {MAX_NAME} caracteres.")

    if description and len(description) > MAX_DESCRIPTION:
        raise FormError(f"Descrição: máximo de {MAX_DESCRIPTION} caracteres.")

    # "Explorador" e "explorador" são a mesma insígnia
    duplicate = db.query(Badge.id).filter(func.lower(Badge.name) == name.lower())
    if badge is not None:
        duplicate = duplicate.filter(Badge.id != badge.id)
    if duplicate.first():
        raise FormError("Já existe uma insígnia com esse nome.")

    if rule_locked and badge is not None:
        rule = badge.rule_type
        object_id, theme_id, count = badge.object_id, badge.theme_id, badge.required_count
        route_id = badge.route_id
    else:
        rule, object_id, theme_id, count, route_id = _rule(db, draft, badge)

    return BadgeData(
        name=name,
        description=description,
        rule_type=rule,
        object_id=object_id,
        theme_id=theme_id,
        required_count=count,
        active=draft.active,
        route_id=route_id,
    )


# ---------- 3. Gravação ----------

def apply_badge(badge: Badge, data: BadgeData) -> None:
    badge.name = data.name
    badge.description = data.description
    badge.rule_type = data.rule_type
    badge.object_id = data.object_id
    badge.theme_id = data.theme_id
    badge.required_count = data.required_count
    badge.route_id = data.route_id
    badge.active = data.active
