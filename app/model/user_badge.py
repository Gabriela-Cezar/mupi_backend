from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, func
from sqlalchemy.orm import relationship

from app.database.database import Base


class UserBadge(Base):
    __tablename__ = "user_badges"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True
    )

    badge_id = Column(
        Integer,
        ForeignKey("badges.id", ondelete="CASCADE"),
        primary_key=True
    )

    collected_at_object_id = Column(
        Integer,
        ForeignKey("mupi_objects.id", ondelete="SET NULL"),
        nullable=True
    )

    collected_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    badge = relationship("Badge")
    mupi_object = relationship("MupiObject")

    __table_args__ = (
        Index("ix_user_badges_badge_id", "badge_id"),
    )