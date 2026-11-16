from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database.database import Base


class MupiObject(Base):
    __tablename__ = "mupi_objects"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(
        String(150),
        nullable=False
    )

    latitude = Column(
        Float,
        nullable=False
    )

    longitude = Column(
        Float,
        nullable=False
    )

    active = Column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
        index=True
    )

    # "Existe individualmente" (PT-09). Se falso, o ponto só aparece dentro
    # de rotas: fica fora do mapa, da busca e dos pontos próximos.
    standalone = Column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False
    )

    # Chave da foto no S3 (PT-05, INF-04). Uma foto por ponto.
    photo_key = Column(
        String(300),
        nullable=True
    )

    # Áudio do ponto no S3 (PT-06): no máximo um, opcional. MP3 ou M4A.
    audio_key = Column(
        String(300),
        nullable=True
    )

    # Duração do áudio em segundos, para o app mostrar antes de tocar
    audio_duration = Column(Integer, nullable=True)

    # Informações de estabelecimento (PT-08), todas opcionais
    address = Column(String(300), nullable=True)

    opening_hours = Column(Text, nullable=True)

    accessibility = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Vários temas por ponto (PT-03)
    themes = relationship(
        "Theme",
        secondary="mupi_object_themes",
        order_by="Theme.name"
    )

    # Blocos de texto (PT-04), já ordenados
    sections = relationship(
        "MupiObjectSection",
        back_populates="object",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MupiObjectSection.position"
    )

    # Vídeos do YouTube (PT-07), já ordenados
    videos = relationship(
        "MupiObjectVideo",
        back_populates="object",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MupiObjectVideo.position"
    )

    # Insígnias de visita deste ponto (INS-01); a ligação fica na insígnia
    badges = relationship(
        "Badge",
        back_populates="mupi_object",
        order_by="Badge.name",
    )

    __table_args__ = (
        CheckConstraint(
            "latitude BETWEEN -90 AND 90",
            name="ck_mupi_objects_latitude_range"
        ),
        CheckConstraint(
            "longitude BETWEEN -180 AND 180",
            name="ck_mupi_objects_longitude_range"
        ),
        Index("ix_mupi_objects_lat_lng", "latitude", "longitude"),
    )
