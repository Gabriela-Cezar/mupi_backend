"""Sessões do app canceladas pela versão, sem depender da senha (USR-05)."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import SECRET_KEY
from app.core.security import (
    ALGORITHM,
    create_access_token,
    create_reset_token,
    decode_access_token,
    token_version_matches,
)
from app.model.user import User
from app.service.auth_service import gerar_password_hash, revoke_sessions

EMAIL = "ana@exemplo.com"
SENHA = "senha-antiga-123"
NOVA_SENHA = "senha-nova-456"


@pytest.fixture
def ana(db_session):
    user = User(email=EMAIL, password_hash=gerar_password_hash(SENHA), email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def perfil(client, token):
    return client.get("/users/me", headers={"Authorization": f"Bearer {token}"})


def token_manual(user_id, **campos):
    payload = {
        "sub": str(user_id),
        "purpose": "access",
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
        **campos,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def login(client, senha=SENHA):
    return client.post("/auth/login", json={"email": EMAIL, "password": senha})


def redefinir_senha(client, reset_token, senha=NOVA_SENHA):
    return client.post(
        "/auth/reset-password", json={"reset_token": reset_token, "password": senha}
    )


# ---------- Conteúdo do token ----------

def test_token_leva_a_versao_e_nada_da_senha(ana):
    payload = decode_access_token(create_access_token(ana.id, 7))

    assert payload["ver"] == 7
    assert "fp" not in payload


@pytest.mark.parametrize("versao_no_token, versao_atual, aceito", [
    (0, 0, True),
    (3, 3, True),
    (2, 3, False),   # token de antes da última mudança
    (4, 3, False),
    (None, 0, False),    # token antigo, sem versão
    ("0", 0, False),
    (True, 1, False),    # True vale 1 no Python, mas não é versão
    (False, 0, False),
    (1.0, 1, False),
])
def test_comparacao_da_versao(versao_no_token, versao_atual, aceito):
    payload = {} if versao_no_token is None else {"ver": versao_no_token}

    assert token_version_matches(payload, versao_atual) is aceito


def test_usuario_novo_comeca_na_versao_zero(db_session):
    user = User(email="novo@exemplo.com", password_hash="x")
    db_session.add(user)
    db_session.commit()

    assert user.token_version == 0


def test_revoke_sessions_soma_um(ana):
    revoke_sessions(ana)
    revoke_sessions(ana)

    assert ana.token_version == 2


# ---------- Uso nas rotas do app ----------

def test_token_da_versao_atual_funciona(client, ana):
    assert perfil(client, create_access_token(ana.id, 0)).status_code == 200


def test_cancelar_as_sessoes_derruba_o_token(client, db_session, ana):
    token = create_access_token(ana.id, ana.token_version)

    revoke_sessions(ana)
    db_session.commit()

    resposta = perfil(client, token)
    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "Sessão inválida ou expirada. Entre novamente."


def test_depois_de_cancelar_um_login_novo_funciona(client, db_session, ana):
    revoke_sessions(ana)
    db_session.commit()

    resposta = login(client)

    assert resposta.status_code == 200
    token = resposta.json()["access_token"]
    assert decode_access_token(token)["ver"] == 1
    assert perfil(client, token).status_code == 200


def test_token_antigo_com_impressao_da_senha_nao_vale_mais(client, ana):
    """Tokens emitidos antes da USR-05 (com "fp", sem "ver"): o usuário entra de novo."""
    import hashlib

    fp = hashlib.sha256(ana.password_hash.encode()).hexdigest()[:16]

    assert perfil(client, token_manual(ana.id, fp=fp)).status_code == 401


def test_versao_true_nao_passa_por_1(client, db_session, ana):
    ana.token_version = 1
    db_session.commit()

    assert perfil(client, token_manual(ana.id, ver=True)).status_code == 401


def test_sessao_nao_depende_do_hash_da_senha(client, db_session, ana):
    """Contas só Google não têm senha; a sessão vale pela versão."""
    token = create_access_token(ana.id, ana.token_version)

    ana.password_hash = "outro-hash"   # sem revoke_sessions
    db_session.commit()

    assert perfil(client, token).status_code == 200


def test_usuario_desativado_continua_bloqueado(client, db_session, ana):
    token = create_access_token(ana.id, ana.token_version)

    ana.is_active = False
    db_session.commit()

    assert perfil(client, token).status_code == 401


# ---------- Redefinir a senha cancela as sessões ----------

def test_redefinir_senha_derruba_as_sessoes_abertas(client, db_session, ana):
    sessao_do_celular = login(client).json()["access_token"]
    reset_token = create_reset_token(ana.email, ana.token_version)

    assert redefinir_senha(client, reset_token).status_code == 200

    db_session.refresh(ana)
    assert ana.token_version == 1
    assert perfil(client, sessao_do_celular).status_code == 401


def test_depois_de_redefinir_entra_com_a_senha_nova(client, ana):
    redefinir_senha(client, create_reset_token(ana.email, ana.token_version))

    assert login(client, SENHA).status_code == 401
    novo = login(client, NOVA_SENHA)
    assert novo.status_code == 200
    assert perfil(client, novo.json()["access_token"]).status_code == 200


def test_link_de_recuperacao_vale_uma_vez_so(client, ana):
    reset_token = create_reset_token(ana.email, ana.token_version)

    primeira = redefinir_senha(client, reset_token)
    segunda = redefinir_senha(client, reset_token, "outra-senha-789")

    assert primeira.status_code == 200
    assert segunda.status_code == 400
    assert segunda.json()["detail"] == "Token de recuperação inválido ou expirado."


def test_cancelar_sessoes_tambem_invalida_links_de_recuperacao(client, db_session, ana):
    reset_token = create_reset_token(ana.email, ana.token_version)

    revoke_sessions(ana)
    db_session.commit()

    assert redefinir_senha(client, reset_token).status_code == 400


def test_link_de_recuperacao_nao_depende_do_hash_da_senha(client, db_session, ana):
    reset_token = create_reset_token(ana.email, ana.token_version)

    ana.password_hash = "outro-hash"   # sem revoke_sessions
    db_session.commit()

    assert redefinir_senha(client, reset_token).status_code == 200


def test_fluxo_completo_de_recuperacao_pela_api(client, db_session, ana, emails_enviados):
    from tests.conftest import codigo_do_ultimo_email

    sessao_antiga = login(client).json()["access_token"]
    client.post("/auth/recovery-password", json={"email": EMAIL})
    codigo = codigo_do_ultimo_email(emails_enviados)
    reset_token = client.post(
        "/auth/verify-recovery-code", json={"email": EMAIL, "codigo": codigo}
    ).json()["reset_token"]

    assert redefinir_senha(client, reset_token).status_code == 200
    assert perfil(client, sessao_antiga).status_code == 401
    assert login(client, NOVA_SENHA).status_code == 200
