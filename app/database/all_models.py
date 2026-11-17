"""Importa todos os models, para o Base.metadata conhecer todas as tabelas.

Usado pelas migrações (Alembic). Ao criar um model novo, importe-o aqui.
"""
from app.database.database import Base  # noqa: F401
from app.model.admin import Admin  # noqa: F401
from app.model.badge import Badge  # noqa: F401
from app.model.email_code import EmailCode  # noqa: F401
from app.model.mupi_object import MupiObject  # noqa: F401
from app.model.mupi_object_section import MupiObjectSection  # noqa: F401
from app.model.mupi_object_theme import MupiObjectTheme  # noqa: F401
from app.model.mupi_object_video import MupiObjectVideo  # noqa: F401
from app.model.theme import Theme  # noqa: F401
from app.model.user import User  # noqa: F401
from app.model.user_badge import UserBadge  # noqa: F401
from app.model.user_visit import UserVisit  # noqa: F401
from app.model.route import Route, RoutePoint, RouteTheme  # noqa: F401
from app.model.user_route_completion import UserRouteCompletion  # noqa: F401
from app.model.user_active_route import UserActiveRoute  # noqa: F401
from app.model.route_event import RouteEvent  # noqa: F401
from app.model.route_point_content import RoutePointContent, RoutePointSection, RoutePointVideo  # noqa: F401
