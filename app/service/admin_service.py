from sqlalchemy.orm import Session

from app.model.admin import Admin
from app.service.auth_service import gerar_password_hash, normalize_email, password_hash

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# Hash fictício para o tempo de resposta não revelar se o e-mail existe
_DUMMY_HASH = password_hash.hash("senha-ficticia-de-admin")


def get_admin_by_email(db: Session, email: str) -> Admin | None:
    return (
        db.query(Admin)
        .filter(Admin.email == normalize_email(email))
        .first()
    )


def authenticate_admin(db: Session, email: str, password: str) -> Admin | None:
    admin = get_admin_by_email(db, email)

    if admin is None:
        password_hash.verify(password, _DUMMY_HASH)
        return None

    if not password_hash.verify(password, admin.password_hash):
        return None

    if not admin.is_active:
        return None

    return admin


def validate_admin_data(email: str, password: str) -> str:
    """Valida e devolve o e-mail normalizado. Lança ValueError com a mensagem."""
    email = normalize_email(email)

    local, _, domain = email.partition("@")

    if not local or "." not in domain or " " in email:
        raise ValueError("E-mail inválido.")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres."
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"A senha deve ter no máximo {MAX_PASSWORD_LENGTH} caracteres."
        )

    return email


def create_admin(db: Session, email: str, password: str) -> Admin:
    email = validate_admin_data(email, password)

    if get_admin_by_email(db, email) is not None:
        raise ValueError("Já existe um administrador com esse e-mail.")

    admin = Admin(email=email, password_hash=gerar_password_hash(password))

    db.add(admin)
    db.commit()
    db.refresh(admin)

    return admin


def set_admin_password(db: Session, admin: Admin, password: str) -> Admin:
    """Troca a senha e reativa o admin. As sessões abertas deixam de valer."""
    validate_admin_data(admin.email, password)

    admin.password_hash = gerar_password_hash(password)
    admin.is_active = True

    db.commit()
    db.refresh(admin)

    return admin
