from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func

from app.database.database import Base


class RouteEventKind:
    STARTED = "started"
    ABANDONED = "abandoned"
    COMPLETED = "completed"
    # Encerrada porque o administrador mudou ou desativou a rota (ROT-10)
    CANCELLED = "cancelled"


class RouteEvent(Base):
    """Rota iniciada, abandonada, concluída ou encerrada pelo painel: base
    para as estatísticas de rotas (observação do ADM-10). A conta excluída
    leva junto os eventos dela (as estatísticas deixam de contá-la)."""
    __tablename__ = "route_events"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    route_id = Column(Integer, ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)

    kind = Column(String(20), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_route_events_route_kind", "route_id", "kind"),
        Index("ix_route_events_user_id", "user_id"),
    )
