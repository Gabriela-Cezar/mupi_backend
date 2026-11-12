from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, func

from app.database.database import Base


class UserVisit(Base):
    __tablename__ = "user_visits"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True
    )

    object_id = Column(
        Integer,
        ForeignKey("mupi_objects.id", ondelete="RESTRICT"),  # FAL-11: preserva o histórico
        primary_key=True
    )

    visited_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    __table_args__ = (
        Index("ix_user_visits_object_id", "object_id"),
    )