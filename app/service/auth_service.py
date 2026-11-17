from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.model.user import User

password_hash = PasswordHash.recommended()

_DUMMY_HASH = password_hash.hash("senha-ficticia-nao-usada")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def gerar_password_hash(password: str) -> str:
    return password_hash.hash(password)


def get_user_by_email(db: Session, email: str) -> User | None:
    return (
        db.query(User)
        .filter(User.email == normalize_email(email))
        .first()
    )


def create_user(
    db: Session,
    email: str,
    hashed_password: str
) -> User | None:
    email = normalize_email(email)

    if get_user_by_email(db, email):
        return None

    user = User(
        email=email,
        password_hash=hashed_password,
        email_verified=True  
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None

    db.refresh(user)

    return user


def check_password(stored_hash: str | None, password: str) -> bool:
    """A senha confere. Sem senha (conta só com Google), confere contra um
    hash fictício: a resposta leva o mesmo tempo e não revela nada."""
    if stored_hash is None:
        password_hash.verify(password, _DUMMY_HASH)
        return False

    return password_hash.verify(password, stored_hash)


def authenticate_user(
    db: Session,
    email: str,
    password: str
) -> User | None:
    user = get_user_by_email(db, email)

    if user is None:
        password_hash.verify(password, _DUMMY_HASH)
        return None

    # Conta só com Google (sem senha) recebe a mesma resposta de senha
    # errada, e no mesmo tempo, para não revelar que existe (USR-03)
    if not check_password(user.password_hash, password):
        return None

    if not user.is_active:
        return None

    return user

def revoke_sessions(user: User) -> None:
    """Cancela todos os tokens já emitidos para o usuário (USR-05).

    Vale para as sessões do app e para os links de recuperação de senha.
    Chamar ao redefinir ou trocar a senha e ao excluir a conta.
    Não faz commit: quem chama decide quando confirmar.
    """
    user.token_version = (user.token_version or 0) + 1
