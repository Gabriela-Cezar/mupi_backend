from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, func

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

    # Onde o usuário estava ao registrar a visita (VIS-03): para análise de
    # fraude e para ajustar a distância máxima no beta. Nulos nas visitas
    # anteriores à migração 0009.
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # Precisão do GPS informada pelo celular, em metros (nula se não veio)
    accuracy = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_user_visits_object_id", "object_id"),
    )