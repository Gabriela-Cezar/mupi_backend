"""Limite de tentativas de login do app (FAL-08)."""
import pytest
from fastapi.testclient import TestClient

from app.controller import auth_controller
from app.core.rate_limit import RateLimiter
from app.model.user import User
from app.service.auth_service import gerar_password_hash
from tests.conftest import BASE_URL, LIMITADORES_DE_LOGIN
from tests.test_email_rate_limit import Relogio

EMAIL = "ana@exemplo.com"
SENHA = "senha-certa-123"
POR_EMAIL = auth_controller.LOGIN_FAILURES_PER_IP_AND_EMAIL   # 5
POR_REDE = auth_controller.LOGIN_FAILURES_PER_IP              # 20
JANELA = auth_controller.LOGIN_WINDOW_SECONDS                 # 15 min


@pytest.fixture
def relogio(monkeypatch):
    relogio = Relogio()
    for limiter in LIMITADORES_DE_LOGIN:
        monkeypatch.setattr(limiter, "clock", relogio)
    return relogio


@pytest.fixture
def ana(db_session):
    db_session.add(User(email=EMAIL, password_hash=gerar_password_hash(SENHA)))
    db_session.commit()


def entrar(client, email=EMAIL, senha=SENHA):
    return client.post("/auth/login", json={"email": email, "password": senha})


def errar(client, vezes, email=EMAIL):
    for _ in range(vezes):
        assert entrar(client, email, "senha-errada").status_code == 401


@pytest.fixture
def outra_rede(app_de_teste, emails_enviados):
    with TestClient(app_de_teste, base_url=BASE_URL, client=("203.0.113.7", 5000)) as c:
        yield c


# ---------- Mesmo e-mail, mesma rede ----------

def test_bloqueia_depois_de_5_senhas_erradas_mesmo_com_a_senha_certa(client, relogio, ana):
    errar(client, POR_EMAIL)

    resposta = entrar(client)

    assert resposta.status_code == 429
    assert resposta.json()["detail"] == (
        "Muitas tentativas de login. Aguarde 15 minutos e tente novamente."
    )
    assert resposta.headers["Retry-After"] == str(JANELA)
    assert "access_token" not in resposta.json()


def test_4_erros_e_depois_a_senha_certa_entra(client, relogio, ana):
    errar(client, POR_EMAIL - 1)

    assert entrar(client).status_code == 200


def test_login_certo_zera_as_falhas_do_email(client, relogio, ana):
    errar(client, POR_EMAIL - 1)
    assert entrar(client).status_code == 200

    errar(client, POR_EMAIL - 1)

    assert entrar(client).status_code == 200


def test_libera_depois_de_15_minutos(client, relogio, ana):
    errar(client, POR_EMAIL)

    relogio.avancar(JANELA)

    assert entrar(client).status_code == 200


def test_tentativas_durante_o_bloqueio_nao_prolongam_a_espera(client, relogio, ana):
    errar(client, POR_EMAIL)

    for _ in range(10):
        relogio.avancar(60)
        assert entrar(client).status_code == 429

    relogio.avancar(JANELA - 10 * 60)

    assert entrar(client).status_code == 200


def test_email_com_outra_grafia_conta_como_o_mesmo(client, relogio, ana):
    errar(client, POR_EMAIL, email="  ANA@Exemplo.com ")

    assert entrar(client).status_code == 429


def test_email_sem_conta_tambem_e_limitado(client, relogio):
    errar(client, POR_EMAIL, email="ninguem@exemplo.com")

    resposta = entrar(client, "ninguem@exemplo.com", "qualquer")

    assert resposta.status_code == 429


# ---------- A dona da conta não fica trancada ----------

def test_mesmo_email_de_outra_rede_continua_entrando(client, outra_rede, relogio, ana):
    """Errar de propósito não pode trancar a conta de outra pessoa."""
    errar(client, POR_EMAIL)
    assert entrar(client).status_code == 429

    assert entrar(outra_rede).status_code == 200


def test_outro_email_da_mesma_rede_continua_entrando(client, db_session, relogio, ana):
    db_session.add(User(email="bia@exemplo.com", password_hash=gerar_password_hash(SENHA)))
    db_session.commit()
    errar(client, POR_EMAIL)

    assert entrar(client, "bia@exemplo.com").status_code == 200


# ---------- Mesma rede, muitos e-mails ----------

def test_bloqueia_a_rede_depois_de_20_erros_em_emails_diferentes(client, relogio, ana):
    for i in range(POR_REDE):
        errar(client, 1, email=f"pessoa{i}@exemplo.com")

    resposta = entrar(client)  # e-mail ainda não tentado, senha certa

    assert resposta.status_code == 429
    assert resposta.headers["Retry-After"] == str(JANELA)


def test_login_certo_nao_zera_a_contagem_da_rede(client, relogio, ana):
    for i in range(POR_REDE - 1):
        errar(client, 1, email=f"pessoa{i}@exemplo.com")

    assert entrar(client).status_code == 200
    errar(client, 1, email="mais-uma@exemplo.com")  # 20ª falha da rede

    assert entrar(client).status_code == 429


def test_bloqueio_da_rede_nao_afeta_outra_rede(client, outra_rede, relogio, ana):
    for i in range(POR_REDE):
        errar(client, 1, email=f"pessoa{i}@exemplo.com")

    assert entrar(outra_rede).status_code == 200


# ---------- O que não conta ----------

def test_dados_invalidos_nao_contam_como_tentativa(client, relogio, ana):
    for _ in range(10):
        assert client.post("/auth/login", json={"email": "nao-e-email", "password": "x"}).status_code == 422

    assert entrar(client).status_code == 200


def test_pedidos_de_codigo_nao_contam_para_o_login(client, relogio, ana, emails_enviados):
    for i in range(8):
        client.post("/auth/recovery-password", json={"email": f"p{i}@exemplo.com"})

    assert entrar(client).status_code == 200


# ---------- RateLimiter.forget ----------

def test_forget_esquece_so_a_chave_informada():
    limiter = RateLimiter(1, 60, clock=Relogio())
    limiter.record("a")
    limiter.record("b")

    limiter.forget("a")
    limiter.forget("nao-existe")

    assert limiter.retry_after("a") == 0
    assert limiter.retry_after("b") == 60
