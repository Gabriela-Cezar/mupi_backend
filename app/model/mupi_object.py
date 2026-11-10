from sqlalchemy import (
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
    func,
)
from sqlalchemy.orm import relationship

from app.database.database import Base
from app.model.theme import Theme 


class MupiObject(Base):
    __tablename__ = "mupi_objects"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(
        String(150),
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
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

    theme_id = Column(
        Integer,
        ForeignKey("themes.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

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

    theme = relationship("Theme")

    media = relationship(
        "MupiObjectMedia",
        back_populates="object",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MupiObjectMedia.id"
    )

    badges = relationship(
        "Badge",
        secondary="mupi_object_badges",
        back_populates="objects"
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