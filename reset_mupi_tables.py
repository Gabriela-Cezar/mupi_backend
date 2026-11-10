from sqlalchemy import inspect

from app.database.database import Base, engine
from app.model.badge import Badge
from app.model.midia import MupiObjectMedia
from app.model.mupi_object import MupiObject
from app.model.mupi_object_badge import MupiObjectBadge
from app.model.theme import Theme
from app.model.user import User  # noqa: F401  (não é apagada, mas as FKs dependem dela)
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit

tables = [
    UserBadge.__table__,
    UserVisit.__table__,
    MupiObjectBadge.__table__,
    MupiObjectMedia.__table__,
    Badge.__table__,
    MupiObject.__table__,
    Theme.__table__,
]

Base.metadata.drop_all(bind=engine, tables=tables)
Base.metadata.create_all(bind=engine)

print("Banco:", engine.url.render_as_string(hide_password=True))
print("Tabelas:", sorted(inspect(engine).get_table_names()))