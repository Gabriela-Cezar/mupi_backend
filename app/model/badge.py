from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

from app.database.database import Base


class BadgeRule(str, Enum):
    """Como a insígnia é conquistada (INS-01)."""

    # Visitar um ponto específico (object_id)
    POINT_VISIT = "point_visit"
    # Visitar N pontos quaisquer
    VISIT_COUNT = "visit_count"
    # Visitar N pontos de um tema (theme_id)
    THEME_VISIT_COUNT = "theme_visit_count"
    # Concluir uma rota específica (route_id) — INS-04
    ROUTE_COMPLETION = "route_completion"


# Cada tipo usa só os seus campos (INS-01)
BADGE_RULE_CHECK = (
    "(rule_type = 'point_visit' AND object_id IS NOT NULL "
    "AND required_count IS NULL AND theme_id IS NULL AND route_id IS NULL) "
    "OR (rule_type = 'visit_count' AND required_count IS NOT NULL "
    "AND required_count >= 1 AND object_id IS NULL AND theme_id IS NULL "
    "AND route_id IS NULL) "
    "OR (rule_type = 'theme_visit_count' AND required_count IS NOT NULL "
    "AND required_count >= 1 AND theme_id IS NOT NULL AND object_id IS NULL "
    "AND route_id IS NULL) "
    "OR (rule_type = 'route_completion' AND route_id IS NOT NULL "
    "AND object_id IS NULL AND theme_id IS NULL AND required_count IS NULL)"
)


class Badge(Base):
    __tablename__ = "badges"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String(100),
        unique=True,
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
    )

    # Chave da imagem no S3 (INF-04)
    image_key = Column(
        String(300),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    rule_type = Column(
        SQLEnum(
            BadgeRule,
            name="badge_rule",
            native_enum=False,
            length=30,
            values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False
    )

    required_count = Column(Integer, nullable=True)

    theme_id = Column(
        Integer,
        ForeignKey("themes.id", ondelete="RESTRICT"),
        nullable=True
    )

    # Ponto da insígnia de visita (INS-01): exatamente um. RESTRICT: ponto
    # com insígnia não pode ser excluído (ADM-09), só desativado.
    object_id = Column(
        Integer,
        ForeignKey("mupi_objects.id", ondelete="RESTRICT"),
        nullable=True
    )

    # Rota da insígnia de conclusão (INS-04). Única: uma rota tem no máximo
    # uma insígnia de conclusão. RESTRICT: rota com insígnia não pode ser
    # excluída (ADM-09), só desativada.
    route_id = Column(
        Integer,
        ForeignKey("routes.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )

    # Desativada: deixa de ser concedida e some do perfil de quem não a
    # tem; quem já conquistou continua com ela (INS-08, FAL-11)
    active = Column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False
    )

    mupi_object = relationship("MupiObject", back_populates="badges")

    theme = relationship("Theme")

    route = relationship("Route")

    __table_args__ = (
        CheckConstraint(
            BADGE_RULE_CHECK,
            name="ck_badges_rule_consistency"
        ),
        Index("ix_badges_object_id", "object_id"),
    )