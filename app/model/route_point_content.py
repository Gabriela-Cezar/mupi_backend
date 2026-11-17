from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.core.youtube import watch_url
from app.database.database import Base


class RoutePointContent(Base):
    """Conteúdo próprio de um ponto dentro de uma rota.

    Quem abre o ponto fazendo esta rota vê este conteúdo no lugar do
    conteúdo normal do ponto. Sem este registro, vale o conteúdo do ponto.

    - nome e foto: opcionais; em branco, valem os do ponto;
    - blocos de texto, áudio, vídeos e informações do local: substituem os
      do ponto (vazios = a rota não mostra aquilo).

    Fica ligado ao par rota + ponto (e não à linha da ordem dos pontos, que
    é recriada ao reordenar). Sair da rota apaga o conteúdo do ponto nela.
    A localização é sempre a do ponto.
    """
    __tablename__ = "route_point_contents"

    id = Column(Integer, primary_key=True)

    route_id = Column(Integer, ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)

    object_id = Column(Integer, ForeignKey("mupi_objects.id", ondelete="CASCADE"), nullable=False)

    # Em branco = o do ponto
    name = Column(String(150), nullable=True)
    photo_key = Column(String(300), nullable=True)

    audio_key = Column(String(300), nullable=True)
    audio_duration = Column(Integer, nullable=True)

    address = Column(String(300), nullable=True)
    opening_hours = Column(Text, nullable=True)
    accessibility = Column(Text, nullable=True)

    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sections = relationship(
        "RoutePointSection",
        order_by="RoutePointSection.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    videos = relationship(
        "RoutePointVideo",
        order_by="RoutePointVideo.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    route = relationship("Route")
    mupi_object = relationship("MupiObject")

    __table_args__ = (
        UniqueConstraint("route_id", "object_id", name="uq_route_point_contents_route_object"),
        Index("ix_route_point_contents_object_id", "object_id"),
    )

    @property
    def file_keys(self) -> list[str]:
        return [key for key in (self.photo_key, self.audio_key) if key]


class RoutePointSection(Base):
    """Bloco de texto do ponto nesta rota (como MupiObjectSection)."""
    __tablename__ = "route_point_sections"

    id = Column(Integer, primary_key=True)

    content_id = Column(
        Integer, ForeignKey("route_point_contents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    position = Column(Integer, nullable=False)
    title = Column(String(150), nullable=False)
    body = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("content_id", "position", name="uq_route_point_sections_content_position"),
    )


class RoutePointVideo(Base):
    """Vídeo do YouTube do ponto nesta rota (como MupiObjectVideo)."""
    __tablename__ = "route_point_videos"

    id = Column(Integer, primary_key=True)

    content_id = Column(
        Integer, ForeignKey("route_point_contents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    position = Column(Integer, nullable=False)
    youtube_id = Column(String(20), nullable=False)
    title = Column(String(150), nullable=True)

    @property
    def url(self) -> str:
        return watch_url(self.youtube_id)

    __table_args__ = (
        UniqueConstraint("content_id", "position", name="uq_route_point_videos_content_position"),
    )
