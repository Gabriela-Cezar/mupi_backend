from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core import admin_auth
from app.core.admin_auth import CSRF_HEADER, SESSION_COOKIE
from app.core.config import SECRET_KEY
from app.core.security import (
    ALGORITHM,
    ADMIN_SESSION_HOURS,
    create_access_token,
    create_admin_session_token,
    csrf_token_for,
    decode_admin_session_token,
)
from app.model.badge import Badge
from app.model.mupi_object import MupiObject
from app.model.theme import Theme
from app.service.admin_service import set_admin_password
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_SENHA,
    csrf_da_sessao,
    fazer_login,
)

HTML = {"accept": "text/html,application/xhtml+xml"}

PAGINAS = ["/admin/mupi-objects", "/admin/badges", "/admin/themes/new"]

ROTAS_JSON = ["/admin/themes", "/admin/search?name=a"]

ENVIOS = {
    "/admin/themes": {"name": "Arte Deco"},
    "/admin/badges": {"name": "Explorador"},
    "/admin/mupi-objects": {
        "name": "Ponto",
        "latitude": "-23.55",
        "longitude": "-46.63",
    },
}


def nada_foi_criado(db_session):
    db_session.expire_all()
    return (
        db_session.query(Theme).count() == 0
        and db_session.query(Badge).count() == 0
        and db_session.query(MupiObject).count() == 0
    )


def usar_sessao(client, token):
    """Envia exatamente este token de sessão nas próximas requisições."""
    client.cookies.clear()
    client.headers["cookie"] = f"{SESSION_COOKIE}={token}"


def sessao_valida_diferente(admin):
    """Outra sessão válida do mesmo admin (com outra data de expiração)."""
    payload = {
        "sub": str(admin.id),
        "purpose": "admin_session",
        "fp": decode_admin_session_token(
            create_admin_session_token(admin.id, admin.password_hash)
        )["fp"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ---------- Sem login ----------

@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_sem_login_redireciona_para_o_login(client, pagina):
    resposta = client.get(pagina, headers=HTML, follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/admin/login?next={pagina}"


def test_redirecionamento_preserva_a_busca(client):
    resposta = client.get("/admin/search?name=teatro", headers=HTML, follow_redirects=False)

    assert resposta.headers["location"] == "/admin/login?next=/admin/search%3Fname%3Dteatro"


@pytest.mark.parametrize("rota", PAGINAS + ROTAS_JSON)
def test_rota_sem_login_fora_do_navegador_retorna_401(client, rota):
    resposta = client.get(rota)

    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "Faça login no painel administrativo."


@pytest.mark.parametrize("rota, dados", ENVIOS.items())
def test_envio_sem_login_retorna_401_e_nao_grava(client, db_session, rota, dados):
    resposta = client.post(rota, data=dados)

    assert resposta.status_code == 401
    assert nada_foi_criado(db_session)


def test_arquivos_estaticos_do_painel_continuam_abertos(client):
    """A tela de login precisa do CSS antes de o admin entrar."""
    assert client.get("/admin-static/style.css").status_code == 200


# ---------- Página de login ----------

def test_pagina_de_login_abre(client):
    resposta = client.get("/admin/login?next=/admin/badges")

    assert resposta.status_code == 200
    assert 'name="email"' in resposta.text
    assert 'name="password"' in resposta.text
    assert 'name="next" value="/admin/badges"' in resposta.text


def test_pagina_de_login_com_sessao_valida_vai_direto_ao_painel(admin_client):
    resposta = admin_client.get("/admin/login", follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/admin/mupi-objects"


# ---------- Login ----------

def test_login_correto_cria_sessao_segura(client, admin):
    resposta = fazer_login(client)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/admin/mupi-objects"

    cookie = resposta.headers["set-cookie"].lower()
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/admin" in cookie
    assert f"max-age={ADMIN_SESSION_HOURS * 3600}" in cookie


def test_depois_do_login_as_paginas_abrem(client, admin):
    fazer_login(client)

    for pagina in PAGINAS:
        resposta = client.get(pagina, headers=HTML)
        assert resposta.status_code == 200, pagina
        assert ADMIN_EMAIL in resposta.text
        assert 'action="/admin/logout"' in resposta.text


def test_login_aceita_email_com_maiusculas_e_espacos(client, admin):
    resposta = fazer_login(client, email="  ADMIN@Mupi.com ")

    assert resposta.status_code == 303


def test_login_volta_para_a_pagina_pedida(client, admin):
    resposta = fazer_login(client, next="/admin/themes/new")

    assert resposta.headers["location"] == "/admin/themes/new"


@pytest.mark.parametrize("destino", [
    "https://site-malicioso.com",
    "//site-malicioso.com",
    "/\\site-malicioso.com",
    "/mupi-objects",
    "/admin/login",
    "",
])
def test_login_nao_redireciona_para_fora_do_painel(client, admin, destino):
    resposta = fazer_login(client, next=destino)

    assert resposta.headers["location"] == "/admin/mupi-objects"


@pytest.mark.parametrize("email, senha", [
    (ADMIN_EMAIL, "senha-errada"),
    ("nao-existe@mupi.com", ADMIN_SENHA),
    (ADMIN_EMAIL, ""),
    ("", ADMIN_SENHA),
])
def test_login_invalido_mostra_erro_sem_criar_sessao(client, admin, email, senha):
    resposta = fazer_login(client, email=email, senha=senha)

    assert resposta.status_code == 401
    assert "E-mail ou senha inválidos." in resposta.text
    assert SESSION_COOKIE not in resposta.headers.get("set-cookie", "")


def test_login_invalido_mantem_o_email_digitado(client, admin):
    resposta = fazer_login(client, senha="senha-errada")

    assert f'value="{ADMIN_EMAIL}"' in resposta.text


def test_admin_desativado_nao_entra(client, db_session, admin):
    admin.is_active = False
    db_session.commit()

    resposta = fazer_login(client)

    assert resposta.status_code == 401


def test_usuario_do_app_nao_entra_no_painel(client, db_session):
    """Contas do aplicativo e administradores são cadastros separados."""
    from app.model.user import User
    from app.service.auth_service import gerar_password_hash

    db_session.add(User(email="usuario@mupi.com", password_hash=gerar_password_hash("senha-123")))
    db_session.commit()

    resposta = fazer_login(client, email="usuario@mupi.com", senha="senha-123")

    assert resposta.status_code == 401


# ---------- Limite de tentativas ----------

def test_bloqueia_apos_5_tentativas_erradas(client, admin):
    for _ in range(admin_auth.MAX_FAILED_LOGINS):
        assert fazer_login(client, senha="senha-errada").status_code == 401

    resposta = fazer_login(client)  # mesmo com a senha certa

    assert resposta.status_code == 429
    assert "Muitas tentativas" in resposta.text


def test_bloqueio_vale_so_para_aquele_email(client, db_session, admin):
    from app.model.admin import Admin
    from app.service.auth_service import gerar_password_hash

    db_session.add(Admin(email="outro@mupi.com", password_hash=gerar_password_hash("outra-senha")))
    db_session.commit()

    for _ in range(admin_auth.MAX_FAILED_LOGINS):
        fazer_login(client, senha="senha-errada")

    assert fazer_login(client, email="outro@mupi.com", senha="outra-senha").status_code == 303


def test_login_correto_zera_as_tentativas(client, admin):
    for _ in range(admin_auth.MAX_FAILED_LOGINS - 1):
        fazer_login(client, senha="senha-errada")

    assert fazer_login(client).status_code == 303

    for _ in range(admin_auth.MAX_FAILED_LOGINS - 1):
        fazer_login(client, senha="senha-errada")

    assert fazer_login(client).status_code == 303


def test_tentativas_antigas_expiram(client, admin, monkeypatch):
    for _ in range(admin_auth.MAX_FAILED_LOGINS):
        fazer_login(client, senha="senha-errada")

    agora = admin_auth.time.monotonic()
    monkeypatch.setattr(
        admin_auth.time,
        "monotonic",
        lambda: agora + admin_auth.FAILED_LOGIN_WINDOW_SECONDS + 1,
    )

    assert fazer_login(client).status_code == 303


# ---------- Validade da sessão ----------

def test_sessao_adulterada_e_recusada(client, admin):
    fazer_login(client)
    token = client.cookies.get(SESSION_COOKIE)
    cabecalho, conteudo, assinatura = token.split(".")
    usar_sessao(client, f"{cabecalho}.{conteudo}.{assinatura[::-1]}")

    assert client.get("/admin/themes").status_code == 401


def test_sessao_expirada_e_recusada(client, admin):
    payload = {
        "sub": str(admin.id),
        "purpose": "admin_session",
        "fp": "qualquer",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    usar_sessao(client, jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM))

    assert client.get("/admin/themes").status_code == 401


def test_token_do_aplicativo_nao_serve_como_sessao_do_painel(client, admin):
    usar_sessao(client, create_access_token(admin.id, 0))

    assert client.get("/admin/themes").status_code == 401


def test_token_assinado_com_outra_chave_e_recusado(client, admin):
    payload = {
        "sub": str(admin.id),
        "purpose": "admin_session",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    usar_sessao(client, jwt.encode(payload, "outra-chave", algorithm=ALGORITHM))

    assert client.get("/admin/themes").status_code == 401


def test_trocar_a_senha_encerra_as_sessoes(admin_client, db_session, admin):
    assert admin_client.get("/admin/themes").status_code == 200

    set_admin_password(db_session, admin, "uma-senha-nova")

    assert admin_client.get("/admin/themes").status_code == 401


def test_desativar_o_admin_encerra_as_sessoes(admin_client, db_session, admin):
    admin.is_active = False
    db_session.commit()

    assert admin_client.get("/admin/themes").status_code == 401


def test_sessao_valida_criada_direto_funciona(client, admin):
    usar_sessao(client, create_admin_session_token(admin.id, admin.password_hash))

    assert client.get("/admin/themes").status_code == 200


# ---------- Proteção CSRF ----------

@pytest.fixture
def logado_sem_csrf(client, admin):
    """Admin logado, mas sem enviar o token CSRF automaticamente."""
    fazer_login(client)
    return client


@pytest.mark.parametrize("rota, dados", ENVIOS.items())
def test_envio_sem_token_csrf_retorna_403_e_nao_grava(logado_sem_csrf, db_session, rota, dados):
    resposta = logado_sem_csrf.post(rota, data=dados)

    assert resposta.status_code == 403
    assert "Recarregue a página" in resposta.json()["detail"]
    assert nada_foi_criado(db_session)


def test_envio_com_token_csrf_errado_retorna_403(logado_sem_csrf, db_session):
    resposta = logado_sem_csrf.post(
        "/admin/themes", data={"name": "Arte Deco", "csrf_token": "token-falso"}
    )

    assert resposta.status_code == 403
    assert nada_foi_criado(db_session)


def test_token_csrf_no_formulario_funciona(logado_sem_csrf, db_session):
    """É assim que os formulários HTML enviam o token."""
    resposta = logado_sem_csrf.post(
        "/admin/themes",
        data={"name": "Arte Deco", "csrf_token": csrf_da_sessao(logado_sem_csrf)},
    )

    assert resposta.status_code == 200
    assert db_session.query(Theme).count() == 1


def test_token_csrf_no_formulario_com_arquivo_funciona(logado_sem_csrf, db_session):
    resposta = logado_sem_csrf.post(
        "/admin/badges",
        data={"name": "Explorador", "csrf_token": csrf_da_sessao(logado_sem_csrf)},
        files={"image": ("", b"", "application/octet-stream")},
    )

    assert resposta.status_code == 200
    assert db_session.query(Badge).count() == 1


def test_token_csrf_no_cabecalho_funciona(logado_sem_csrf, db_session):
    resposta = logado_sem_csrf.post(
        "/admin/themes",
        data={"name": "Arte Deco"},
        headers={CSRF_HEADER: csrf_da_sessao(logado_sem_csrf)},
    )

    assert resposta.status_code == 200


def test_token_csrf_de_outra_sessao_nao_serve(logado_sem_csrf, db_session, admin):
    token_csrf_antigo = csrf_da_sessao(logado_sem_csrf)
    outra_sessao = sessao_valida_diferente(admin)
    usar_sessao(logado_sem_csrf, outra_sessao)

    assert csrf_token_for(outra_sessao) != token_csrf_antigo

    com_antigo = logado_sem_csrf.post(
        "/admin/themes", data={"name": "Arte Deco", "csrf_token": token_csrf_antigo}
    )
    com_o_certo = logado_sem_csrf.post(
        "/admin/themes",
        data={"name": "Arte Deco", "csrf_token": csrf_token_for(outra_sessao)},
    )

    assert com_antigo.status_code == 403
    assert com_o_certo.status_code == 200


def test_formularios_trazem_o_token_csrf_da_sessao(admin_client):
    token = csrf_da_sessao(admin_client)

    for pagina in PAGINAS:
        html = admin_client.get(pagina).text
        # um no formulário da página e um no botão "Sair"
        assert html.count(f'name="csrf_token" value="{token}"') == 2, pagina


# ---------- Sair ----------

def test_sair_encerra_a_sessao(logado_sem_csrf):
    resposta = logado_sem_csrf.post(
        "/admin/logout",
        data={"csrf_token": csrf_da_sessao(logado_sem_csrf)},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/admin/login"
    assert logado_sem_csrf.cookies.get(SESSION_COOKIE) is None
    assert logado_sem_csrf.get("/admin/themes").status_code == 401


def test_sair_exige_token_csrf(logado_sem_csrf):
    resposta = logado_sem_csrf.post("/admin/logout", follow_redirects=False)

    assert resposta.status_code == 403
    assert logado_sem_csrf.get("/admin/themes").status_code == 200


def test_sair_sem_login_retorna_401(client):
    assert client.post("/admin/logout").status_code == 401
