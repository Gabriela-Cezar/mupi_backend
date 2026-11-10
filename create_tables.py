from app.database.database import Base, engine
from app.model.badge import Badge
from app.model.midia import MupiObjectMedia
from app.model.mupi_object import MupiObject
from app.model.mupi_object_badge import MupiObjectBadge

tables = [
    MupiObjectBadge.__table__,
    MupiObjectMedia.__table__,
    Badge.__table__,
    MupiObject.__table__,
]

Base.metadata.drop_all(bind=engine, tables=tables)
Base.metadata.create_all(bind=engine)

print("Tabelas recriadas.")