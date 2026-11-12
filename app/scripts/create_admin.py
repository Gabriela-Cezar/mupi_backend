"""Cria um administrador do painel ou redefine a senha de um existente.

Uso (na raiz do projeto):
    python -m app.scripts.create_admin
"""
from getpass import getpass

from sqlalchemy import inspect

from app.database.database import SessionLocal, engine
from app.model.admin import Admin
from app.service.admin_service import (
    create_admin,
    get_admin_by_email,
    set_admin_password,
    validate_admin_data,
)


def ask_password() -> str:
    while True:
        password = getpass("Senha (mínimo 8 caracteres): ")
        confirmation = getpass("Repita a senha: ")

        if password != confirmation:
            print("As senhas não conferem. Tente novamente.\n")
            continue

        try:
            validate_admin_data("validacao@exemplo.com", password)
        except ValueError as error:
            print(f"{error}\n")
            continue

        return password


MIGRATIONS_MISSING = (
    "A tabela de administradores não existe neste banco. "
    "Aplique as migrações primeiro (na raiz do projeto):\n"
    "    alembic upgrade head"
)


def admins_table_exists(bind=engine) -> bool:
    return inspect(bind).has_table(Admin.__tablename__)


def main() -> None:
    # As tabelas são criadas só pelas migrações (FAL-14)
    if not admins_table_exists():
        print(f"Erro: {MIGRATIONS_MISSING}")
        raise SystemExit(1)

    email = input("E-mail do administrador: ").strip()

    db = SessionLocal()

    try:
        existing = get_admin_by_email(db, email)

        if existing is not None:
            answer = input(
                f"Já existe um administrador com o e-mail {existing.email}. "
                "Deseja redefinir a senha? (s/N): "
            )

            if answer.strip().lower() != "s":
                print("Nada foi alterado.")
                return

            set_admin_password(db, existing, ask_password())
            print(f"Senha de {existing.email} redefinida. Sessões abertas foram encerradas.")
            return

        admin = create_admin(db, email, ask_password())
        print(f"Administrador {admin.email} criado com sucesso.")

    except ValueError as error:
        print(f"Erro: {error}")
        raise SystemExit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
