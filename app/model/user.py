from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

from app.database.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    email_verified = Column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False
    )

    # Vazio na conta criada pelo login com Google (USR-04); a recuperação de
    # senha permite criar uma depois (USR-06)
    password_hash = Column(
        String(255),
        nullable=True
    )

    # Identificador da conta Google ("sub" do id_token), quando vinculada
    google_sub = Column(
        String(255),
        unique=True,
        nullable=True
    )

    # Muda (+1) para cancelar todas as sessões e links de recuperação já
    # emitidos: ao redefinir a senha, ao excluir a conta... (USR-05)
    token_version = Column(
        Integer,
        default=0,
        server_default="0",
        nullable=False
    )

    is_active = Column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False
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