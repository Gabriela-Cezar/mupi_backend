import pytest

from app.controller import email_controller
from tests.conftest import ADMIN_EMAIL, fazer_login

URL = "/admin/email-test"
HTML = {"accept": "text/html"}


@pytest.fixture
def envios(monkeypatch):
    """Substitui o envio real e guarda o que seria enviado."""
    registro = {"enviados": [], "resultado": True}

    def send_email_falso(recipient, subject, html_content):
        registro["enviados"].append({
            "recipient": recipient,
            "subject": subject,
            "html_content": html_content,
        })
        return registro["resultado"]

    monkeypatch.setattr(email_controller, "send_email", send_email_falso)
    return registro


# ---------- Rota antiga ----------

def test_rota_antiga_aberta_nao_existe_mais(client, envios):
    resposta = client.post("/email/test", params={"recipient": "alguem@exemplo.com"})

    assert resposta.status_code == 404
    assert envios["enviados"] == []


# ---------- Sem permissão ----------

def test_pagina_sem_login_redireciona_para_o_login(client):
    resposta = client.get(URL, headers=HTML, follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/admin/login?next={URL}"


def test_envio_sem_login_retorna_401_e_nao_envia(client, envios):
    resposta = client.post(URL, data={"recipient": "alguem@exemplo.com"})

    assert resposta.status_code == 401
    assert envios["enviados"] == []


def test_envio_sem_token_csrf_retorna_403_e_nao_envia(client, admin, envios):
    fazer_login(client)

    resposta = client.post(URL, data={"recipient": "alguem@exemplo.com"})

    assert resposta.status_code == 403
    assert envios["enviados"] == []


# ---------- Página ----------

def test_pagina_sugere_o_email_do_admin(admin_client):
    resposta = admin_client.get(URL)

    assert resposta.status_code == 200
    assert 'action="/admin/email-test"' in resposta.text
    assert f'value="{ADMIN_EMAIL}"' in resposta.text


def test_barra_do_painel_tem_link_para_o_teste(admin_client):
    html = admin_client.get("/admin/themes/new").text

    assert f'href="{URL}"' in html


# ---------- Envio ----------

def test_envia_o_email_de_teste(admin_client, envios):
    resposta = admin_client.post(URL, data={"recipient": " teste@exemplo.com "})

    assert resposta.status_code == 200
    assert "E-mail de teste enviado para teste@exemplo.com." in resposta.text
    assert envios["enviados"] == [{
        "recipient": "teste@exemplo.com",
        "subject": email_controller.TEST_SUBJECT,
        "html_content": email_controller.TEST_HTML,
    }]


@pytest.mark.parametrize("destinatario", ["", "   ", "nao-e-email", "a@", "@exemplo.com"])
def test_email_invalido_mostra_erro_e_nao_envia(admin_client, envios, destinatario):
    resposta = admin_client.post(URL, data={"recipient": destinatario})

    assert resposta.status_code == 400
    assert "Informe um e-mail válido." in resposta.text
    assert envios["enviados"] == []


def test_email_invalido_mantem_o_que_foi_digitado(admin_client, envios):
    resposta = admin_client.post(URL, data={"recipient": "nao-e-email"})

    assert 'value="nao-e-email"' in resposta.text


def test_sem_campo_destinatario_mostra_erro(admin_client, envios):
    resposta = admin_client.post(URL, data={})

    assert resposta.status_code == 400
    assert envios["enviados"] == []


def test_falha_no_resend_mostra_erro(admin_client, envios):
    envios["resultado"] = False

    resposta = admin_client.post(URL, data={"recipient": "teste@exemplo.com"})

    assert resposta.status_code == 502
    assert "Falha ao enviar o e-mail" in resposta.text
    assert "E-mail de teste enviado" not in resposta.text
    assert len(envios["enviados"]) == 1


def test_destinatario_com_html_e_escapado(admin_client, envios):
    resposta = admin_client.post(URL, data={"recipient": '"><script>x</script>'})

    assert "<script>x</script>" not in resposta.text
