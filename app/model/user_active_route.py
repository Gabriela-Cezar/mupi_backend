from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import relationship

from app.database.database import Base


class CancelReason:
    """Por que o progresso foi encerrado sem o usuário pedir (ROT-10)."""

    # O administrador mudou os pontos ou a ordem da rota
    ROUTE_UPDATED = "route_updated"
    # A rota foi desativada (pelo administrador ou porque um ponto dela foi)
    ROUTE_DEACTIVATED = "route_deactivated"


class UserActiveRoute(Base):
    """Rota que o usuário está fazendo (ROT-05). No máximo uma por usuário:
    a chave é o próprio usuário.

    `next_index` é a posição, na ordem da rota, do próximo ponto a
    finalizar; igual ao número de pontos = todos finalizados.

    Se o administrador mudar os pontos ou desativar a rota, o progresso fica
    com `cancelled_reason` (ROT-10): na próxima consulta o app recebe o aviso
    "inicie novamente" e o progresso é apagado.
    """
    __tablename__ = "user_active_routes"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    route_id = Column(
        Integer,
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
    )

    next_index = Column(Integer, default=0, server_default="0", nullable=False)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cancelled_reason = Column(String(30), nullable=True)

    route = relationship("Route")

    __table_args__ = (
        Index("ix_user_active_routes_route_id", "route_id"),
    )
