from datetime import datetime, timezone

from app.service import auth_user_email_service as codigos
from tests.conftest import passar_intervalo_de_reenvio

EMAIL = "ana@exemplo.com"
HASH_SENHA = "hash-da-senha"


def test_sem_cadastro_pendente_retorna_none_sem_espera():
    assert codigos.renovar_codigo(EMAIL) == (None, 0)


def test_dentro_do_intervalo_informa_segundos_de_espera():
    codigos.gerar_codigo(EMAIL, HASH_SENHA)

    codigo, espera = codigos.renovar_codigo(EMAIL)

    assert codigo is None
    assert 1 <= espera <= codigos.RESEND_COOLDOWN_SECONDS


def test_dentro_do_intervalo_nao_altera_o_codigo_atual():
    original = codigos.gerar_codigo(EMAIL, HASH_SENHA)

    codigos.renovar_codigo(EMAIL)

    assert codigos.codigos_verificacao[EMAIL]["codigo"] == original


def test_apos_intervalo_gera_novo_codigo_de_seis_digitos(monkeypatch):
    codigos.gerar_codigo(EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(EMAIL)
    monkeypatch.setattr(codigos, "_novo_codigo", lambda: "222222")

    codigo, espera = codigos.renovar_codigo(EMAIL)

    assert (codigo, espera) == ("222222", 0)
    assert codigos.codigos_verificacao[EMAIL]["codigo"] == "222222"


def test_codigo_gerado_tem_seis_digitos():
    codigos.gerar_codigo(EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(EMAIL)

    codigo, _ = codigos.renovar_codigo(EMAIL)

    assert codigo.isdigit() and len(codigo) == 6


def test_apos_intervalo_mantem_senha_e_renova_prazo_e_tentativas():
    codigos.gerar_codigo(EMAIL, HASH_SENHA)
    dados = codigos.codigos_verificacao[EMAIL]
    dados["tentativas"] = 3
    expira_antes = dados["expira_em"]
    passar_intervalo_de_reenvio(EMAIL)
    enviado_antes = dados["enviado_em"]

    codigos.renovar_codigo(EMAIL)

    assert dados["password_hash"] == HASH_SENHA
    assert dados["tentativas"] == 0
    assert dados["expira_em"] >= expira_antes
    assert dados["enviado_em"] > enviado_antes
    assert dados["enviado_em"] <= datetime.now(timezone.utc)


def test_novo_envio_reinicia_o_intervalo():
    codigos.gerar_codigo(EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(EMAIL)
    codigos.renovar_codigo(EMAIL)

    codigo, espera = codigos.renovar_codigo(EMAIL)

    assert codigo is None
    assert espera > 0


def test_codigo_antigo_deixa_de_valer_e_o_novo_cria_a_conta(monkeypatch):
    monkeypatch.setattr(codigos, "_novo_codigo", lambda: "111111")
    codigos.gerar_codigo(EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(EMAIL)
    monkeypatch.setattr(codigos, "_novo_codigo", lambda: "222222")
    codigos.renovar_codigo(EMAIL)

    valido_antigo, _, _ = codigos.verificar_codigo(EMAIL, "111111")
    valido_novo, _, senha = codigos.verificar_codigo(EMAIL, "222222")

    assert valido_antigo is False
    assert valido_novo is True
    assert senha == HASH_SENHA


def test_codigo_expirado_pode_ser_renovado():
    """Se o código expirou, o usuário ainda deve conseguir pedir outro."""
    codigos.gerar_codigo(EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(EMAIL)
    dados = codigos.codigos_verificacao[EMAIL]
    dados["expira_em"] = datetime.now(timezone.utc).replace(year=2000)

    codigo, _ = codigos.renovar_codigo(EMAIL)

    assert codigo is not None
    assert codigos.verificar_codigo(EMAIL, codigo)[0] is True


def test_email_e_normalizado():
    codigos.gerar_codigo("  Ana@Exemplo.COM ", HASH_SENHA)
    passar_intervalo_de_reenvio(EMAIL)

    codigo, _ = codigos.renovar_codigo("ANA@exemplo.com")

    assert codigo is not None
