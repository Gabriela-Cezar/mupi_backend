from sqlalchemy import Column, ForeignKey, Index, Integer

from app.database.database import Base


class MupiObjectBadge(Base):
    __tablename__ = "mupi_object_badges"

    object_id = Column(
        Integer,
        ForeignKey("mupi_objects.id", ondelete="CASCADE"),
        primary_key=True
    )

    badge_id = Column(
        Integer,
        ForeignKey("badges.id", ondelete="CASCADE"),
        primary_key=True
    )

    __table_args__ = (
        Index("ix_mupi_object_badges_badge_id", "badge_id"),
    )