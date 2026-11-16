from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

from app.database.database import Base


class RouteDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class AgeRating(str, Enum):
    """Classificação indicativa, nas faixas do sistema brasileiro (ROT-01)."""
    FREE = "L"
    AGE_10 = "10"
    AGE_12 = "12"
    AGE_14 = "14"
    AGE_16 = "16"
    AGE_18 = "18"


def _enum(enum, name):
    return SQLEnum(
        enum,
        name=name,
        native_enum=False,
        length=10,
        values_callable=lambda e: [m.value for m in e],
    )


class Route(Base):
    """Rota: sequência fixa de pontos ligada por um trajeto a pé (ROT-01).

    O trajeto é calculado uma vez pelo OpenRouteService ao salvar a rota e
    reutilizado por todos os usuários (ROT-03).
    """
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True)

    name = Column(String(150), unique=True, nullable=False)

    description = Column(Text, nullable=True)

    # Capa no S3 (INF-04); obrigatória para ativar
    cover_key = Column(String(300), nullable=True)

    difficulty = Column(_enum(RouteDifficulty, "route_difficulty"), nullable=False)

    age_rating = Column(_enum(AgeRating, "route_age_rating"), nullable=False)

    # Nova rota começa desativada: só ativa com capa, 2+ pontos e trajeto
    active = Column(Boolean, default=False, server_default="0", nullable=False)

    # ---------- Trajeto (ROT-03), calculado ----------

    # Coordenadas [longitude, latitude] do primeiro ao último ponto
    path = Column(JSON, nullable=True)

    # Índice, em `path`, de cada ponto da rota, na ordem: o trecho do ponto
    # i ao i+1 é path[waypoints[i]:waypoints[i+1] + 1]
    waypoints = Column(JSON, nullable=True)

    distance_m = Column(Float, nullable=True)

    # Tempo só de caminhada, do OpenRouteService
    walk_seconds = Column(Integer, nullable=True)

    # Último erro do cálculo; com erro a rota fica sem trajeto
    path_error = Column(Text, nullable=True)

    path_computed_at = Column(DateTime(timezone=True), nullable=True)

    # Tempo estimado mostrado no app, em minutos. Editável: a caminhada não
    # inclui o tempo em cada ponto. Vazio = o tempo de caminhada.
    estimated_minutes = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    points = relationship(
        "RoutePoint",
        order_by="RoutePoint.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    themes = relationship(
        "Theme",
        secondary="route_themes",
        order_by="Theme.name",
    )

    __table_args__ = (
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes >= 1",
            name="ck_routes_estimated_minutes",
        ),
    )

    @property
    def has_path(self) -> bool:
        return bool(self.path) and self.path_error is None

    @property
    def minutes(self) -> int | None:
        """Tempo mostrado no app: o estimado, ou o de caminhada."""
        if self.estimated_minutes:
            return self.estimated_minutes
        if self.walk_seconds is not None:
            return max(1, round(self.walk_seconds / 60))
        return None

    @property
    def point_ids(self) -> list[int]:
        return [rp.object_id for rp in self.points]


class RoutePoint(Base):
    """Ponto da rota, na ordem (ROT-02). O mesmo ponto pode estar em várias
    rotas, mas não duas vezes na mesma. RESTRICT: ponto de uma rota não pode
    ser excluído (ADM-09), só desativado."""
    __tablename__ = "route_points"

    id = Column(Integer, primary_key=True)

    route_id = Column(
        Integer,
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
    )

    object_id = Column(
        Integer,
        ForeignKey("mupi_objects.id", ondelete="RESTRICT"),
        nullable=False,
    )

    position = Column(Integer, nullable=False)

    mupi_object = relationship("MupiObject")

    __table_args__ = (
        UniqueConstraint("route_id", "position", name="uq_route_points_route_position"),
        UniqueConstraint("route_id", "object_id", name="uq_route_points_route_object"),
        Index("ix_route_points_object_id", "object_id"),
    )


class RouteTheme(Base):
    """Ligação rota ↔ tema. Excluir a rota ou o tema remove só a ligação."""
    __tablename__ = "route_themes"

    route_id = Column(
        Integer,
        ForeignKey("routes.id", ondelete="CASCADE"),
        primary_key=True,
    )

    theme_id = Column(
        Integer,
        ForeignKey("themes.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        Index("ix_route_themes_theme_id", "theme_id"),
    )
