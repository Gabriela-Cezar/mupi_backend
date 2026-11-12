"""Sessão de 30 dias renovada a cada abertura do app (USR-11)."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.controller import auth_controller
from app.core.config import SECRET_KEY
from app.core.security import (
    ACCESS_TOKEN_DAYS,
    ALGORITHM,
    create_access_token,
    create_admin_session_token,
    create_reset_token,
    decode_access_token,
)
from app.model.user import User
from app.service.auth_service import gerar_password_hash, revoke_sessions
from tests.test_email_rate_limit import Relogio

URL = "/auth/refresh"
EMAIL = "ana@exemplo.com"
SENHA = "senha-certa-123"
POR_HORA = auth_controller.REFRESH_PER_USER        # 30
JANELA = auth_controller.REFRESH_WINDOW_SECONDS    # 1 hora


@pytest.fixture
def ana(db_session):
    user = User(email=EMAIL, password_hash=gerar_password_hash(SENHA), email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def token(ana):
    return create_access_token(ana.id, ana.token_version)


@pytest.fixture
def relogio(monkeypatch):
    relogio = Relogio()
    monkeypatch.setattr(auth_controller.refresh_limiter, "clock", relogio)
    return relogio


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def renovar(client, token):
    return client.post(URL, headers=bearer(token))


def perfil(client, token):
    return client.get("/users/me", headers=bearer(token))


def validade_em_dias(token):
    exp = decode_access_token(token)["exp"]
    restante = datetime.fromtimestamp(exp, timezone.utc) - datetime.now(timezone.utc)
    return restante.total_seconds() / 86400


def jwt_manual(chave=SECRET_KEY, **payload):
    return jwt.encode(payload, chave, algorithm=ALGORITHM)


# ---------- Renovação com token válido ----------

def test_token_valido_recebe_um_novo(client, ana, token):
    resposta = renovar(client, token)

    assert resposta.status_code == 200
    dados = resposta.json()
    assert set(dados) == {"message", "access_token", "token_type", "user_id", "email"}
    assert dados["message"] == "Sessão renovada"
    assert dados["token_type"] == "bearer"
    assert dados["user_id"] == ana.id
    assert dados["email"] == EMAIL


def test_resposta_tem_o_mesmo_formato_do_login(client, ana, token):
    login = client.post("/auth/login", json={"email": EMAIL, "password": SENHA}).json()
    renovacao = renovar(client, token).json()

    assert set(login) == set(renovacao)


def test_token_novo_funciona_nas_rotas_do_app(client, token):
    novo = renovar(client, token).json()["access_token"]

    assert perfil(client, novo).status_code == 200


def test_token_novo_vale_30_dias(client, token):
    novo = renovar(client, token).json()["access_token"]

    assert ACCESS_TOKEN_DAYS == 30
    assert 29.99 < validade_em_dias(novo) <= 30


def test_token_novo_leva_a_versao_atual(client, db_session, ana):
    ana.token_version = 4
    db_session.commit()

    novo = renovar(client, create_access_token(ana.id, 4)).json()["access_token"]

    assert decode_access_token(novo)["ver"] == 4


def test_renovar_um_token_quase_vencido_estende_a_sessao(client, ana):
    """O caso do app aberto no 29º dia: ganha mais 30 dias."""
    quase_vencido = jwt_manual(
        sub=str(ana.id), purpose="access", ver=0,
        exp=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    novo = renovar(client, quase_vencido).json()["access_token"]

    assert validade_em_dias(novo) > 29.99


def test_token_antigo_continua_valendo_ate_expirar(client, token):
    renovar(client, token)

    assert perfil(client, token).status_code == 200


def test_login_tambem_entrega_token_de_30_dias(client, ana):
    token = client.post("/auth/login", json={"email": EMAIL, "password": SENHA}).json()["access_token"]

    assert 29.99 < validade_em_dias(token) <= 30


# ---------- Recusas (401) ----------

def recusado(resposta):
    return (
        resposta.status_code == 401
        and resposta.json()["detail"] == "Sessão inválida ou expirada. Entre novamente."
        and "access_token" not in resposta.json()
    )


def test_sem_token(client):
    assert recusado(client.post(URL))


def test_token_expirado(client, ana):
    vencido = jwt_manual(
        sub=str(ana.id), purpose="access", ver=0,
        exp=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    assert recusado(renovar(client, vencido))


def test_token_adulterado(client, token):
    cabecalho, corpo, assinatura = token.split(".")
    trocado = "A" if assinatura[0] != "A" else "B"

    assert recusado(renovar(client, f"{cabecalho}.{corpo}.{trocado}{assinatura[1:]}"))


def test_token_assinado_com_outra_chave(client, ana):
    falso = jwt_manual(
        chave="outra-chave", sub=str(ana.id), purpose="access", ver=0,
        exp=datetime.now(timezone.utc) + timedelta(days=1),
    )

    assert recusado(renovar(client, falso))


def test_token_de_recuperacao_de_senha_nao_renova(client, ana):
    assert recusado(renovar(client, create_reset_token(ana.email, ana.token_version)))


def test_sessao_do_painel_nao_renova(client, ana):
    assert recusado(renovar(client, create_admin_session_token(ana.id, ana.password_hash)))


def test_usuario_desativado(client, db_session, ana, token):
    ana.is_active = False
    db_session.commit()

    assert recusado(renovar(client, token))


def test_usuario_que_nao_existe_mais(client):
    assert recusado(renovar(client, create_access_token(999, 0)))


def test_depois_de_cancelar_as_sessoes(client, db_session, ana, token):
    revoke_sessions(ana)
    db_session.commit()

    assert recusado(renovar(client, token))


def test_depois_de_redefinir_a_senha(client, ana, token):
    reset = create_reset_token(ana.email, ana.token_version)
    client.post("/auth/reset-password", json={"reset_token": reset, "password": "senha-nova-456"})

    assert recusado(renovar(client, token))


def test_renovar_nao_ressuscita_sessao_cancelada(client, db_session, ana, token):
    """Um token renovado antes do cancelamento também cai junto."""
    novo = renovar(client, token).json()["access_token"]

    revoke_sessions(ana)
    db_session.commit()

    assert recusado(renovar(client, novo))
    assert perfil(client, novo).status_code == 401


# ---------- Limite de renovações por usuário ----------

def test_ate_30_renovacoes_por_hora(client, relogio, token):
    respostas = [renovar(client, token).status_code for _ in range(POR_HORA)]

    assert respostas == [200] * POR_HORA


def test_a_31a_renovacao_na_hora_e_recusada(client, relogio, token):
    for _ in range(POR_HORA):
        renovar(client, token)

    resposta = renovar(client, token)

    assert resposta.status_code == 429
    assert resposta.headers["Retry-After"] == str(JANELA)
    assert resposta.json()["detail"] == (
        "Muitas renovações de sessão. Aguarde 60 minutos e tente novamente."
    )


def test_bloqueio_nao_derruba_a_sessao(client, relogio, token):
    """Com 429 o app continua usando o token que já tem."""
    for _ in range(POR_HORA + 1):
        renovar(client, token)

    assert perfil(client, token).status_code == 200


def test_limite_libera_depois_de_uma_hora(client, relogio, token):
    for _ in range(POR_HORA):
        renovar(client, token)

    relogio.avancar(JANELA)

    assert renovar(client, token).status_code == 200


def test_limite_e_por_usuario(client, db_session, relogio, token):
    for _ in range(POR_HORA):
        renovar(client, token)
    beto = User(email="beto@exemplo.com", password_hash="x", email_verified=True)
    db_session.add(beto)
    db_session.commit()

    resposta = renovar(client, create_access_token(beto.id, 0))

    assert resposta.status_code == 200


def test_tokens_diferentes_do_mesmo_usuario_somam_no_limite(client, relogio, ana, token):
    """Renovar com o token novo não zera a contagem."""
    atual = token
    for _ in range(POR_HORA):
        atual = renovar(client, atual).json()["access_token"]

    assert renovar(client, atual).status_code == 429


def test_tentativas_sem_token_valido_nao_gastam_o_limite_de_ninguem(client, relogio, token):
    for _ in range(POR_HORA + 5):
        client.post(URL, headers=bearer("lixo"))

    assert renovar(client, token).status_code == 200
