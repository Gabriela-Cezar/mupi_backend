from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

from app.database.database import Base


class BadgeRule(str, Enum):
    MANUAL = "manual"                        
    VISIT_COUNT = "visit_count"              
    THEME_VISIT_COUNT = "theme_visit_count" 


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
        nullable=False,
        default=BadgeRule.MANUAL,
        server_default=BadgeRule.MANUAL.value
    )

    required_count = Column(Integer, nullable=True)

    theme_id = Column(
        Integer,
        ForeignKey("themes.id", ondelete="RESTRICT"),
        nullable=True
    )

    objects = relationship(
        "MupiObject",
        secondary="mupi_object_badges",
        back_populates="badges"
    )

    theme = relationship("Theme")

    __table_args__ = (
        CheckConstraint(
            "(rule_type = 'manual' AND required_count IS NULL "
            "AND theme_id IS NULL) "
            "OR (rule_type = 'visit_count' AND required_count >= 1 "
            "AND theme_id IS NULL) "
            "OR (rule_type = 'theme_visit_count' AND required_count >= 1 "
            "AND theme_id IS NOT NULL)",
            name="ck_badges_rule_consistency"
        ),
    )