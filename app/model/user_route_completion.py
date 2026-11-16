from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, func

from app.database.database import Base


class UserRouteCompletion(Base):
    """Conclusão de rota (ROT-08): uma linha por conclusão, inclusive as
    repetidas. Usada para mostrar "concluída" na lista de rotas e para a
    insígnia de rota.

    RESTRICT na rota: rota concluída por alguém não pode ser excluída, só
    desativada (ADM-09). A conta excluída leva junto as conclusões dela.
    """
    __tablename__ = "user_route_completions"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    route_id = Column(
        Integer,
        ForeignKey("routes.id", ondelete="RESTRICT"),
        nullable=False,
    )

    completed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_user_route_completions_user_route", "user_id", "route_id"),
        Index("ix_user_route_completions_route_id", "route_id"),
    )
