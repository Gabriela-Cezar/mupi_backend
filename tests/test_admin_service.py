import pytest

from app.model.admin import Admin
from app.service.admin_service import (
    authenticate_admin,
    create_admin,
    get_admin_by_email,
    set_admin_password,
)
from app.service.auth_service import password_hash

EMAIL = "gabi@mupi.com"
SENHA = "senha-segura"


# ---------- Criação ----------

def test_cria_admin_com_senha_criptografada(db_session):
    admin = create_admin(db_session, EMAIL, SENHA)

    assert admin.id is not None
    assert admin.email == EMAIL
    assert admin.is_active is True
    assert admin.password_hash != SENHA
    assert password_hash.verify(SENHA, admin.password_hash)


def test_email_e_normalizado(db_session):
    admin = create_admin(db_session, "  Gabi@MUPI.com ", SENHA)

    assert admin.email == EMAIL


def test_nao_cria_admin_repetido(db_session):
    create_admin(db_session, EMAIL, SENHA)

    with pytest.raises(ValueError, match="Já existe"):
        create_admin(db_session, EMAIL.upper(), "outra-senha")

    assert db_session.query(Admin).count() == 1


@pytest.mark.parametrize("senha", ["", "1234567"])
def test_senha_curta_e_recusada(db_session, senha):
    with pytest.raises(ValueError, match="pelo menos 8"):
        create_admin(db_session, EMAIL, senha)

    assert db_session.query(Admin).count() == 0


def test_senha_longa_demais_e_recusada(db_session):
    with pytest.raises(ValueError, match="no máximo 128"):
        create_admin(db_session, EMAIL, "a" * 129)


@pytest.mark.parametrize("email", ["", "sem-arroba", "@mupi.com", "gabi@mupi", "ga bi@mupi.com"])
def test_email_invalido_e_recusado(db_session, email):
    with pytest.raises(ValueError, match="E-mail inválido"):
        create_admin(db_session, email, SENHA)


# ---------- Autenticação ----------

def test_autentica_com_email_e_senha_corretos(db_session):
    create_admin(db_session, EMAIL, SENHA)

    assert authenticate_admin(db_session, EMAIL, SENHA).email == EMAIL


def test_senha_errada_nao_autentica(db_session):
    create_admin(db_session, EMAIL, SENHA)

    assert authenticate_admin(db_session, EMAIL, "senha-errada") is None


def test_email_inexistente_nao_autentica(db_session):
    assert authenticate_admin(db_session, "ninguem@mupi.com", SENHA) is None


def test_admin_desativado_nao_autentica(db_session):
    admin = create_admin(db_session, EMAIL, SENHA)
    admin.is_active = False
    db_session.commit()

    assert authenticate_admin(db_session, EMAIL, SENHA) is None


# ---------- Redefinição de senha ----------

def test_redefine_a_senha(db_session):
    admin = create_admin(db_session, EMAIL, SENHA)

    set_admin_password(db_session, admin, "senha-nova-123")

    assert authenticate_admin(db_session, EMAIL, SENHA) is None
    assert authenticate_admin(db_session, EMAIL, "senha-nova-123") is not None


def test_redefinir_a_senha_reativa_o_admin(db_session):
    admin = create_admin(db_session, EMAIL, SENHA)
    admin.is_active = False
    db_session.commit()

    set_admin_password(db_session, admin, "senha-nova-123")

    assert get_admin_by_email(db_session, EMAIL).is_active is True


def test_redefinir_com_senha_curta_nao_altera(db_session):
    admin = create_admin(db_session, EMAIL, SENHA)

    with pytest.raises(ValueError):
        set_admin_password(db_session, admin, "curta")

    assert authenticate_admin(db_session, EMAIL, SENHA) is not None
