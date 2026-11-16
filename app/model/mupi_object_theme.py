from sqlalchemy import Column, ForeignKey, Index, Integer

from app.database.database import Base


class MupiObjectTheme(Base):
    """Ligação ponto ↔ tema: um ponto pode ter vários temas (PT-03).

    Excluir o ponto ou o tema remove só a ligação.
    """
    __tablename__ = "mupi_object_themes"

    object_id = Column(
        Integer,
        ForeignKey("mupi_objects.id", ondelete="CASCADE"),
        primary_key=True
    )

    theme_id = Column(
        Integer,
        ForeignKey("themes.id", ondelete="CASCADE"),
        primary_key=True
    )

    __table_args__ = (
        Index("ix_mupi_object_themes_theme_id", "theme_id"),
    )
