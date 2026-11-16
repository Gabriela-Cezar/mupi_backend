from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.youtube import watch_url
from app.database.database import Base


class MupiObjectVideo(Base):
    """Vídeo do YouTube do ponto (PT-07). Guarda só o ID do vídeo."""
    __tablename__ = "mupi_object_videos"

    id = Column(Integer, primary_key=True)

    object_id = Column(
        Integer,
        ForeignKey("mupi_objects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    position = Column(Integer, nullable=False)

    youtube_id = Column(String(20), nullable=False)

    title = Column(String(150), nullable=True)

    object = relationship("MupiObject", back_populates="videos")

    @property
    def url(self) -> str:
        return watch_url(self.youtube_id)

    __table_args__ = (
        UniqueConstraint(
            "object_id", "position",
            name="uq_mupi_object_videos_object_position"
        ),
    )
