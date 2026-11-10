from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    Enum as SQLEnum,
    func,
)
from sqlalchemy.orm import deferred, relationship

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

    data = deferred(
        Column(
            LargeBinary,
            nullable=True
        )
    )

    mime_type = Column(
        String(100),
        nullable=True
    )

    url = Column(
        String(500),
        nullable=True
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

    __table_args__ = (
        CheckConstraint(
            "(data IS NOT NULL) <> (url IS NOT NULL)",
            name="ck_mupi_object_media_data_xor_url"
        ),
    )