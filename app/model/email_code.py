from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
)

from app.database.database import Base


class EmailCode(Base):
    """Código de 6 dígitos enviado por e-mail (USR-09 / FAL-13).

    Um por e-mail e finalidade: pedir outro substitui o anterior.
    O código não é guardado, só o hash dele.
    """
    __tablename__ = "email_codes"

    id = Column(Integer, primary_key=True)

    email = Column(String(255), nullable=False)

    # "verificacao" (cadastro) ou "recuperacao" (senha esquecida)
    purpose = Column(String(20), nullable=False)

    code_hash = Column(String(64), nullable=False)

    # Senha escolhida no cadastro: a conta só é criada depois da verificação
    password_hash = Column(String(255), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    attempts = Column(Integer, nullable=False, default=0, server_default="0")

    sent_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("email", "purpose"),
        CheckConstraint(
            "purpose IN ('verificacao', 'recuperacao')",
            name="ck_email_codes_purpose",
        ),
    )
