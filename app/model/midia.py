from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Enum as SQLEnum,
    func,
)
from sqlalchemy.orm import relationship

from app.database.database import Base


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class MupiObjectMedia(Base):
    __tablename__ = "mupi_object_media"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    object_id = Column(
        Integer,
        ForeignKey("mupi_objects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    type = Column(
        SQLEnum(
            MediaType,
            name="media_type",
            values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False
    )

    # Só vídeos ficam aqui; a foto do ponto está em mupi_objects.photo_key (INF-04)
    url = Column(
        String(500),
        nullable=False
    )

    title = Column(
        String(150),
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    object = relationship(
        "MupiObject",
        back_populates="media"
    )
