"""Importa todos os models, para o Base.metadata conhecer todas as tabelas.

Usado pelas migrações (Alembic). Ao criar um model novo, importe-o aqui.
"""
from app.database.database import Base  # noqa: F401
from app.model.admin import Admin  # noqa: F401
from app.model.badge import Badge  # noqa: F401
from app.model.midia import MupiObjectMedia  # noqa: F401
from app.model.mupi_object import MupiObject  # noqa: F401
from app.model.mupi_object_badge import MupiObjectBadge  # noqa: F401
from app.model.theme import Theme  # noqa: F401
from app.model.user import User  # noqa: F401
from app.model.user_badge import UserBadge  # noqa: F401
from app.model.user_visit import UserVisit  # noqa: F401
