from app.model.user import User
from app.service import auth_user_email_service as codigos
from tests.conftest import passar_intervalo_de_reenvio

URL = "/auth/resend-verification"
EMAIL = "ana@exemplo.com"
SENHA = "senha-segura-123"


def cadastrar(client, email=EMAIL):
    resposta = client.post("/auth/register", json={"email": email, "password": SENHA})
    assert resposta.status_code == 200
    return resposta


def test_sem_cadastro_pendente_retorna_404(client, emails_enviados):
    resposta = client.post(URL, json={"email": EMAIL})

    assert resposta.status_code == 404
    assert "Nenhum cadastro pendente" in resposta.json()["detail"]
    assert emails_enviados == []


def test_logo_apos_o_cadastro_retorna_429(client, emails_enviados):
    cadastrar(client)

    resposta = client.post(URL, json={"email": EMAIL})

    assert resposta.status_code == 429
    assert resposta.json()["detail"].startswith("Aguarde")
    assert len(emails_enviados) == 1  # apenas o e-mail do cadastro


def test_apos_o_intervalo_envia_novo_codigo(client, emails_enviados):
    cadastrar(client)
    passar_intervalo_de_reenvio(EMAIL)

    resposta = client.post(URL, json={"email": EMAIL})

    assert resposta.status_code == 200
    assert resposta.json() == {"message": "Novo código enviado."}

    novo_codigo = codigos.codigos_verificacao[EMAIL]["codigo"]
    email = emails_enviados[-1]
    assert len(emails_enviados) == 2
    assert email["recipient"] == EMAIL
    assert email["subject"] == "Código de verificação - MUPI"
    assert novo_codigo in email["html_content"]


def test_dois_reenvios_seguidos_o_segundo_retorna_429(client, emails_enviados):
    cadastrar(client)
    passar_intervalo_de_reenvio(EMAIL)

    primeira = client.post(URL, json={"email": EMAIL})
    segunda = client.post(URL, json={"email": EMAIL})

    assert primeira.status_code == 200
    assert segunda.status_code == 429
    assert len(emails_enviados) == 2


def test_email_com_maiusculas_encontra_o_cadastro(client, emails_enviados):
    cadastrar(client, email="Ana@Exemplo.com")
    passar_intervalo_de_reenvio(EMAIL)

    resposta = client.post(URL, json={"email": "ANA@EXEMPLO.COM"})

    assert resposta.status_code == 200
    assert emails_enviados[-1]["recipient"] == EMAIL


def test_email_invalido_retorna_422(client, emails_enviados):
    resposta = client.post(URL, json={"email": "nao-e-um-email"})

    assert resposta.status_code == 422
    assert emails_enviados == []


def test_sem_corpo_retorna_422(client):
    resposta = client.post(URL)

    assert resposta.status_code == 422


def test_fluxo_completo_cadastro_reenvio_e_verificacao(client, db_session):
    cadastrar(client)
    codigo_antigo = codigos.codigos_verificacao[EMAIL]["codigo"]
    passar_intervalo_de_reenvio(EMAIL)
    client.post(URL, json={"email": EMAIL})
    codigo_novo = codigos.codigos_verificacao[EMAIL]["codigo"]

    if codigo_antigo != codigo_novo:  # chance de 1 em 1 milhão de serem iguais
        com_antigo = client.post(
            "/auth/verify-email", json={"email": EMAIL, "codigo": codigo_antigo}
        )
        assert com_antigo.status_code == 400

    com_novo = client.post(
        "/auth/verify-email", json={"email": EMAIL, "codigo": codigo_novo}
    )

    assert com_novo.status_code == 200
    assert db_session.query(User).filter_by(email=EMAIL).count() == 1


def test_apos_conta_criada_nao_ha_mais_reenvio(client):
    cadastrar(client)
    codigo = codigos.codigos_verificacao[EMAIL]["codigo"]
    client.post("/auth/verify-email", json={"email": EMAIL, "codigo": codigo})

    resposta = client.post(URL, json={"email": EMAIL})

    assert resposta.status_code == 404
