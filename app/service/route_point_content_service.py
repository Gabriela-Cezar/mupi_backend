"""Conteúdo próprio de um ponto dentro de uma rota (ver RoutePointContent)."""
from sqlalchemy.orm import Session, selectinload

from app.model.route import Route
from app.model.route_point_content import RoutePointContent
from app.model.user_active_route import UserActiveRoute


def _options():
    return (
        selectinload(RoutePointContent.sections),
        selectinload(RoutePointContent.videos),
        selectinload(RoutePointContent.route),
    )


def get_content(db: Session, route_id: int, object_id: int) -> RoutePointContent | None:
    return (
        db.query(RoutePointContent)
        .options(*_options())
        .filter(
            RoutePointContent.route_id == route_id,
            RoutePointContent.object_id == object_id,
        )
        .first()
    )


def contents_for_route(db: Session, route_id: int) -> dict[int, RoutePointContent]:
    """Conteúdos próprios da rota, por ponto."""
    rows = (
        db.query(RoutePointContent)
        .options(*_options())
        .filter(RoutePointContent.route_id == route_id)
    )
    return {content.object_id: content for content in rows}


def content_for_user(db: Session, user_id: int, object_id: int) -> RoutePointContent | None:
    """O conteúdo que vale para o usuário ao abrir o ponto: o da rota que
    ele está fazendo, se ela tiver conteúdo próprio para o ponto. Fora de
    rota (ou fazendo outra), None = o conteúdo normal do ponto."""
    progress = (
        db.query(UserActiveRoute)
        .filter(
            UserActiveRoute.user_id == user_id,
            UserActiveRoute.cancelled_reason.is_(None),
        )
        .first()
    )

    if progress is None:
        return None

    return get_content(db, progress.route_id, object_id)


def remove_contents_outside(db: Session, route: Route) -> list[str]:
    """Apaga o conteúdo dos pontos que saíram da rota. Devolve os arquivos
    deles, para apagar do S3 depois de gravar. Não faz commit."""
    keep = set(route.point_ids)
    keys: list[str] = []

    for content in db.query(RoutePointContent).filter(RoutePointContent.route_id == route.id):
        if content.object_id not in keep:
            keys.extend(content.file_keys)
            db.delete(content)

    return keys


def route_file_keys(db: Session, route_id: int) -> list[str]:
    """Arquivos de todos os conteúdos da rota (ao excluir a rota)."""
    keys: list[str] = []
    for content in db.query(RoutePointContent).filter(RoutePointContent.route_id == route_id):
        keys.extend(content.file_keys)
    return keys
