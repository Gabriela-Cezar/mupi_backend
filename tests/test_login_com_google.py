"""Login com Google (USR-04), recuperação em conta só Google (USR-06),
exclusão de conta pelo Google (USR-08) e sair de todos os aparelhos (USR-13)."""
import time

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from app.core import config
from app.core.security import create_access_token, create_reset_token
from app.model.user import User
from app.service.auth_service import gerar_password_hash
from app.service.google_auth_service import (
    GoogleLoginDisabled,
    GoogleTokenError,
    verify_google_token,
)
from tests.google_falso import CLIENT_ID_ANDROID
from tests.test_migrations import alembic_cfg


def entrar(client, token):
    return client.post("/auth/google", json={"id_token": token})


def usuarios(db_session):
    db_session.expire_all()
    return db_session.query(User).all()


# ---------- Validação do token ----------

def test_token_valido_devolve_a_conta(google):
    token = google.conta()

    identidade = verify_google_token(token)

    assert (identidade.sub, identidade.email) == ("google-sub-ana", "ana@gmail.com")


def test_aceita_os_client_ids_do_android_e_do_ios(google):
    token = google.conta(aud=CLIENT_ID_ANDROID)

    assert verify_google_token(token).sub == "google-sub-ana"


@pytest.mark.parametrize("ajuste, mensagem", [
    ({"aud": "outro-app.apps.googleusercontent.com"}, "outro aplicativo"),
    ({"iss": "https://falso.example.com"}, "não foi emitido pelo Google"),
    ({"email_verified": False}, "não foi verificado"),
    ({"sub": ""}, "sem identificação"),
])
def test_tokens_que_nao_valem(google, ajuste, mensagem):
    token = google.conta(**ajuste)

    with pytest.raises(GoogleTokenError, match=mensagem):
        verify_google_token(token)


def test_token_invalido_ou_vencido(google):
    with pytest.raises(GoogleTokenError, match="inválido ou vencido"):
        verify_google_token("qualquer-coisa")


def test_sem_client_ids_o_login_com_google_fica_desligado(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_IDS", [])

    with pytest.raises(GoogleLoginDisabled):
        verify_google_token("x")


# ---------- POST /auth/google ----------

def test_primeiro_login_cria_a_conta_sem_senha(client, db_session, google):
    resposta = entrar(client, google.conta(email="Ana@Gmail.com"))

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["message"] == "Conta criada com sucesso"
    assert dados["email"] == "ana@gmail.com"
    [user] = usuarios(db_session)
    assert user.google_sub == "google-sub-ana"
    assert user.email_verified is True
    assert user.password_hash is None
    # O token serve para o app
    perfil = client.get("/users/me", headers={"Authorization": f"Bearer {dados['access_token']}"})
    assert perfil.json()["email"] == "ana@gmail.com"


def test_segundo_login_entra_na_mesma_conta(client, db_session, google):
    token = google.conta()
    primeiro = entrar(client, token).json()

    segundo = entrar(client, token).json()

    assert segundo["message"] == "Login realizado com sucesso"
    assert segundo["user_id"] == primeiro["user_id"]
    assert len(usuarios(db_session)) == 1


def test_mesmo_email_de_conta_com_senha_vincula_e_mantem_a_senha(client, db_session, google):
    user = User(email="ana@gmail.com", password_hash=gerar_password_hash("Senha-123"), email_verified=False)
    db_session.add(user)
    db_session.commit()

    resposta = entrar(client, google.conta())

    assert resposta.json()["user_id"] == user.id
    [salvo] = usuarios(db_session)
    assert salvo.google_sub == "google-sub-ana"
    assert salvo.email_verified is True
    # Continua entrando pela senha também
    login = client.post("/auth/login", json={"email": "ana@gmail.com", "password": "Senha-123"})
    assert login.status_code == 200


def test_conta_google_entra_pelo_sub_mesmo_se_o_email_mudou(client, db_session, google):
    entrar(client, google.conta(email="antigo@gmail.com"))

    resposta = entrar(client, google.conta(token="outro-token", email="novo@gmail.com"))

    assert len(usuarios(db_session)) == 1
    assert resposta.json()["email"] == "antigo@gmail.com"


def test_token_invalido_responde_401(client, db_session, google):
    resposta = entrar(client, "token-falso")

    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "Token do Google inválido ou vencido."
    assert usuarios(db_session) == []


def test_login_com_google_desligado_responde_503(client):
    resposta = entrar(client, "qualquer")

    assert resposta.status_code == 503
    assert resposta.json()["detail"] == "Login com Google indisponível no momento."


def test_conta_desativada_nao_entra(client, db_session, google):
    entrar(client, google.conta())
    [user] = usuarios(db_session)
    user.is_active = False
    db_session.commit()

    resposta = entrar(client, google.conta())

    assert resposta.status_code == 403


def test_muitos_tokens_invalidos_bloqueiam_a_rede(client, google, monkeypatch):
    from app.controller import auth_controller

    for _ in range(auth_controller.LOGIN_FAILURES_PER_IP):
        entrar(client, "token-falso")

    resposta = entrar(client, google.conta())

    assert resposta.status_code == 429


@pytest.mark.parametrize("corpo", [{}, {"id_token": ""}])
def test_sem_token_responde_422(client, corpo):
    assert client.post("/auth/google", json=corpo).status_code == 422


# ---------- Conta só com Google e a senha (USR-03, USR-01, USR-06) ----------

def test_conta_sem_senha_recebe_a_mesma_resposta_no_login_por_senha(client, google):
    entrar(client, google.conta())

    sem_senha = client.post("/auth/login", json={"email": "ana@gmail.com", "password": "qualquer-1"})
    inexistente = client.post("/auth/login", json={"email": "ninguem@gmail.com", "password": "qualquer-1"})

    assert sem_senha.status_code == inexistente.status_code == 401
    assert sem_senha.json() == inexistente.json() == {"detail": "E-mail ou senha inválidos"}


def test_cadastro_com_email_de_conta_google_avisa_que_ja_existe(client, google):
    entrar(client, google.conta())

    resposta = client.post("/auth/register", json={"email": "ana@gmail.com", "password": "Senha-123"})

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "E-mail já cadastrado"


def test_recuperacao_cria_uma_senha_na_conta_google(client, db_session, google):
    entrar(client, google.conta())
    [user] = usuarios(db_session)

    resposta = client.post("/auth/reset-password", json={
        "reset_token": create_reset_token(user.email, user.token_version),
        "password": "Senha-nova-1",
    })

    assert resposta.status_code == 200
    # Agora entra das duas formas
    assert client.post("/auth/login", json={"email": "ana@gmail.com", "password": "Senha-nova-1"}).status_code == 200
    assert entrar(client, google.conta()).status_code == 200


# ---------- Exclusão de conta pelo Google (USR-08) ----------

def logado(client, db_session):
    [user] = usuarios(db_session)
    client.headers["Authorization"] = f"Bearer {create_access_token(user.id, user.token_version)}"
    return user


def excluir(client, **corpo):
    return client.request("DELETE", "/users/me", json=corpo)


def test_conta_google_exclui_com_id_token_recente(client, db_session, google):
    entrar(client, google.conta())
    logado(client, db_session)

    resposta = excluir(client, id_token=google.conta(token="confirmacao"))

    assert resposta.status_code == 200
    assert usuarios(db_session) == []


def test_id_token_antigo_nao_serve_para_excluir(client, db_session, google):
    entrar(client, google.conta())
    logado(client, db_session)
    antigo = google.conta(token="antigo", iat=int(time.time()) - 3600)

    resposta = excluir(client, id_token=antigo)

    assert resposta.status_code == 403
    assert "Entre com o Google de novo" in resposta.json()["detail"]
    assert len(usuarios(db_session)) == 1


def test_id_token_de_outra_conta_google_nao_serve(client, db_session, google):
    entrar(client, google.conta())
    logado(client, db_session)

    resposta = excluir(client, id_token=google.conta(token="da-bia", sub="google-sub-bia"))

    assert resposta.status_code == 403
    assert len(usuarios(db_session)) == 1


def test_conta_sem_senha_nao_exclui_com_senha(client, db_session, google):
    entrar(client, google.conta())
    logado(client, db_session)

    resposta = excluir(client, password="qualquer")

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Senha incorreta."


def test_conta_so_com_senha_nao_exclui_com_google(client, db_session, google, usuario):
    usuario.email = "ana@gmail.com"
    db_session.commit()
    logado(client, db_session)

    assert excluir(client, id_token=google.conta()).status_code == 403


def test_conta_vinculada_exclui_pelos_dois_jeitos(client, db_session, google):
    entrar(client, google.conta())
    user = logado(client, db_session)
    user.password_hash = gerar_password_hash("Senha-123")
    db_session.commit()

    assert excluir(client, password="Senha-123").status_code == 200


def test_sem_senha_nem_token_responde_422(client, db_session, google):
    entrar(client, google.conta())
    logado(client, db_session)

    resposta = excluir(client)

    assert resposta.status_code == 422


# ---------- Sair de todos os aparelhos (USR-13) ----------

def test_sair_de_todos_os_aparelhos(client, db_session, google):
    token = entrar(client, google.conta()).json()["access_token"]
    outro_aparelho = entrar(client, google.conta()).json()["access_token"]

    resposta = client.post("/users/me/logout-all", headers={"Authorization": f"Bearer {token}"})

    assert resposta.status_code == 200
    for sessao in (token, outro_aparelho):
        assert client.get("/users/me", headers={"Authorization": f"Bearer {sessao}"}).status_code == 401


# ---------- Migração 0016 ----------

def test_desfazer_a_0016_para_se_houver_conta_sem_senha(tmp_path):
    url = f"sqlite:///{tmp_path / 'google.db'}"
    cfg = alembic_cfg(url)
    command.upgrade(cfg, "0016")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (email, google_sub) VALUES ('ana@gmail.com', 'sub-ana')"))

    with pytest.raises(RuntimeError, match="só com Google"):
        command.downgrade(cfg, "0015")

    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET password_hash = 'x'"))

    command.downgrade(cfg, "0015")
    engine.dispose()
