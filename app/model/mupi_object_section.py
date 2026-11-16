from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.database import Base


class MupiObjectSection(Base):
    """Bloco de texto do ponto: título livre + texto simples (PT-04).

    A API devolve os blocos ordenados por `position`; o app exibe o título
    em negrito e pode ler cada bloco em voz alta.
    """
    __tablename__ = "mupi_object_sections"

    id = Column(Integer, primary_key=True)

    object_id = Column(
        Integer,
        ForeignKey("mupi_objects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    position = Column(Integer, nullable=False)

    title = Column(String(150), nullable=False)

    # Texto simples; as quebras de linha são preservadas
    body = Column(Text, nullable=False)

    object = relationship("MupiObject", back_populates="sections")

    __table_args__ = (
        UniqueConstraint(
            "object_id", "position",
            name="uq_mupi_object_sections_object_position"
        ),
    )
