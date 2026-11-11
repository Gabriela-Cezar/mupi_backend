"""Limite de envio de e-mails (FAL-07)."""
import pytest
from fastapi.testclient import TestClient

from app.controller import auth_controller
from app.core.rate_limit import RateLimiter, format_wait
from app.model.user import User
from tests.conftest import BASE_URL, LIMITADORES_DE_EMAIL

SENHA = "senha-segura-123"


class Relogio:
    """Relógio controlado pelo teste (segundos)."""

    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora

    def avancar(self, segundos):
        self.agora += segundos


@pytest.fixture
def relogio(monkeypatch):
    relogio = Relogio()
    for limiter in LIMITADORES_DE_EMAIL:
        monkeypatch.setattr(limiter, "clock", relogio)
    return relogio


def cadastrar(client, email="ana@exemplo.com"):
    return client.post("/auth/register", json={"email": email, "password": SENHA})


def recuperar(client, email="ana@exemplo.com"):
    return client.post("/auth/recovery-password", json={"email": email})


@pytest.fixture
def usuario_ana(db_session):
    db_session.add(User(email="ana@exemplo.com", password_hash="hash"))
    db_session.commit()


# ---------- RateLimiter ----------

class TestRateLimiter:
    def test_permite_ate_o_maximo_e_depois_informa_a_espera(self):
        relogio = Relogio()
        limiter = RateLimiter(2, 60, clock=relogio)

        assert limiter.hit("a") == 0
        assert limiter.hit("a") == 0
        assert limiter.hit("a") == 60

    def test_a_espera_diminui_com_o_tempo_e_libera_depois_da_janela(self):
        relogio = Relogio()
        limiter = RateLimiter(1, 60, clock=relogio)
        limiter.hit("a")

        relogio.avancar(45)
        assert limiter.hit("a") == 15

        relogio.avancar(15)
        assert limiter.hit("a") == 0

    def test_janela_deslizante_libera_um_por_vez(self):
        relogio = Relogio()
        limiter = RateLimiter(2, 60, clock=relogio)
        limiter.hit("a")          # t=0
        relogio.avancar(30)
        limiter.hit("a")          # t=30

        relogio.avancar(31)       # t=61: o primeiro saiu da janela
        assert limiter.hit("a") == 0
        assert limiter.hit("a") == 29  # o de t=30 sai em t=90

    def test_chaves_sao_independentes(self):
        limiter = RateLimiter(1, 60, clock=Relogio())
        limiter.hit("a")

        assert limiter.hit("b") == 0

    def test_tentativa_bloqueada_nao_prolonga_a_espera(self):
        relogio = Relogio()
        limiter = RateLimiter(1, 60, clock=relogio)
        limiter.hit("a")

        for _ in range(5):
            relogio.avancar(10)
            limiter.hit("a")  # bloqueadas

        relogio.avancar(10)   # 60 s desde o único registro
        assert limiter.hit("a") == 0

    def test_retry_after_so_consulta_e_record_registra(self):
        limiter = RateLimiter(1, 60, clock=Relogio())

        assert limiter.retry_after("a") == 0
        assert limiter.retry_after("a") == 0

        limiter.record("a")
        assert limiter.retry_after("a") == 60

    def test_reset_esquece_tudo(self):
        limiter = RateLimiter(1, 60, clock=Relogio())
        limiter.hit("a")

        limiter.reset()

        assert limiter.hit("a") == 0


@pytest.mark.parametrize("segundos, texto", [
    (1, "1 segundo"),
    (45, "45 segundos"),
    (60, "1 minuto"),
    (61, "2 minutos"),
    (900, "15 minutos"),
])
def test_format_wait(segundos, texto):
    assert format_wait(segundos) == texto


# ---------- Cadastro ----------

class TestCadastro:
    def test_segundo_pedido_em_menos_de_60s_retorna_429(self, client, relogio, emails_enviados):
        assert cadastrar(client).status_code == 200

        relogio.avancar(20)
        resposta = cadastrar(client)

        assert resposta.status_code == 429
        assert resposta.json()["detail"] == "Aguarde 40 segundos para pedir outro código."
        assert resposta.headers["Retry-After"] == "40"
        assert len(emails_enviados) == 1

    def test_depois_de_60s_envia_de_novo(self, client, relogio, emails_enviados):
        cadastrar(client)

        relogio.avancar(60)

        assert cadastrar(client).status_code == 200
        assert len(emails_enviados) == 2

    def test_o_limite_vale_para_o_email_com_outra_grafia(self, client, relogio, emails_enviados):
        cadastrar(client, "ana@exemplo.com")

        assert cadastrar(client, "  ANA@Exemplo.com ").status_code == 429

    def test_outro_email_nao_e_bloqueado(self, client, relogio, emails_enviados):
        cadastrar(client, "ana@exemplo.com")

        assert cadastrar(client, "bia@exemplo.com").status_code == 200

    def test_falha_no_envio_nao_conta_o_intervalo(self, client, relogio, monkeypatch, emails_enviados):
        monkeypatch.setattr(auth_controller, "send_email", lambda **_: False)
        assert cadastrar(client).status_code == 503

        monkeypatch.setattr(auth_controller, "send_email", lambda **_: True)
        assert cadastrar(client).status_code == 200

    def test_email_ja_cadastrado_continua_retornando_400(self, client, relogio, usuario_ana):
        assert cadastrar(client).status_code == 400
        assert cadastrar(client).status_code == 400


# ---------- Recuperação de senha ----------

class TestRecuperacao:
    def test_segundo_pedido_em_menos_de_60s_retorna_429(self, client, relogio, usuario_ana, emails_enviados):
        assert recuperar(client).status_code == 200

        resposta = recuperar(client)

        assert resposta.status_code == 429
        assert resposta.json()["detail"] == "Aguarde 1 minuto para pedir outro código."
        assert resposta.headers["Retry-After"] == "60"
        assert len(emails_enviados) == 1

    def test_depois_de_60s_envia_de_novo(self, client, relogio, usuario_ana, emails_enviados):
        recuperar(client)

        relogio.avancar(60)

        assert recuperar(client).status_code == 200
        assert len(emails_enviados) == 2

    def test_nao_revela_quem_tem_conta(self, client, relogio, usuario_ana, emails_enviados):
        """Com conta ou sem conta, as respostas são as mesmas."""
        com_conta = [recuperar(client, "ana@exemplo.com") for _ in range(2)]
        sem_conta = [recuperar(client, "ninguem@exemplo.com") for _ in range(2)]

        assert [r.status_code for r in com_conta] == [200, 429]
        assert [r.status_code for r in sem_conta] == [200, 429]
        assert com_conta[0].json() == sem_conta[0].json()
        assert com_conta[1].json() == sem_conta[1].json()

    def test_novo_codigo_nao_pode_ser_pedido_a_cada_5_tentativas(self, client, relogio, usuario_ana, emails_enviados):
        """Cada código novo zera as tentativas: sem limite, daria para tentar sem fim."""
        recuperar(client)

        for _ in range(5):
            client.post(
                "/auth/verify-recovery-code",
                json={"email": "ana@exemplo.com", "codigo": "000000"},
            )

        assert recuperar(client).status_code == 429


# ---------- Limite por IP ----------

class TestLimitePorIp:
    def test_bloqueia_depois_de_10_pedidos_da_mesma_rede(self, client, relogio, emails_enviados):
        for i in range(auth_controller.EMAIL_REQUESTS_PER_IP):
            assert cadastrar(client, f"pessoa{i}@exemplo.com").status_code == 200

        resposta = cadastrar(client, "mais-uma@exemplo.com")

        assert resposta.status_code == 429
        assert "a partir desta rede" in resposta.json()["detail"]
        assert resposta.json()["detail"].endswith("Aguarde 15 minutos e tente novamente.")
        assert resposta.headers["Retry-After"] == "900"
        assert len(emails_enviados) == auth_controller.EMAIL_REQUESTS_PER_IP

    def test_soma_cadastro_recuperacao_e_reenvio(self, client, relogio, emails_enviados):
        for i in range(5):
            cadastrar(client, f"pessoa{i}@exemplo.com")
        for i in range(4):
            recuperar(client, f"outra{i}@exemplo.com")
        client.post("/auth/resend-verification", json={"email": "x@exemplo.com"})  # 10º

        assert recuperar(client, "mais-uma@exemplo.com").status_code == 429
        assert client.post(
            "/auth/resend-verification", json={"email": "pessoa0@exemplo.com"}
        ).status_code == 429

    def test_libera_depois_de_15_minutos(self, client, relogio, emails_enviados):
        for i in range(auth_controller.EMAIL_REQUESTS_PER_IP):
            cadastrar(client, f"pessoa{i}@exemplo.com")

        relogio.avancar(auth_controller.EMAIL_REQUESTS_WINDOW_SECONDS)

        assert cadastrar(client, "mais-uma@exemplo.com").status_code == 200

    def test_outra_rede_nao_e_afetada(self, client, app_de_teste, relogio, emails_enviados):
        for i in range(auth_controller.EMAIL_REQUESTS_PER_IP):
            cadastrar(client, f"pessoa{i}@exemplo.com")

        with TestClient(app_de_teste, base_url=BASE_URL, client=("203.0.113.7", 5000)) as outra_rede:
            assert cadastrar(outra_rede, "mais-uma@exemplo.com").status_code == 200

    def test_login_e_verificacao_nao_contam(self, client, relogio, emails_enviados):
        """Só as rotas que enviam e-mail contam para o limite por IP."""
        for _ in range(15):
            client.post("/auth/login", json={"email": "a@exemplo.com", "password": "x"})
            client.post("/auth/verify-email", json={"email": "a@exemplo.com", "codigo": "123456"})

        assert cadastrar(client).status_code == 200
