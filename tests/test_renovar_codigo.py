from datetime import datetime, timezone

from app.service import auth_user_email_service as codigos
from tests.conftest import codigo_pendente, passar_intervalo_de_reenvio

EMAIL = "ana@exemplo.com"
HASH_SENHA = "hash-da-senha"


def test_sem_cadastro_pendente_retorna_none_sem_espera(db_session):
    assert codigos.renovar_codigo(db_session, EMAIL) == (None, 0)


def test_dentro_do_intervalo_informa_segundos_de_espera(db_session):
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)

    codigo, espera = codigos.renovar_codigo(db_session, EMAIL)

    assert codigo is None
    assert 1 <= espera <= codigos.RESEND_COOLDOWN_SECONDS


def test_dentro_do_intervalo_nao_altera_o_codigo_atual(db_session):
    original = codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)

    codigos.renovar_codigo(db_session, EMAIL)

    assert codigos.verificar_codigo(db_session, EMAIL, original)[0] is True


def test_apos_intervalo_gera_novo_codigo(db_session, monkeypatch):
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(db_session, EMAIL)
    monkeypatch.setattr(codigos, "_novo_codigo", lambda: "222222")

    codigo, espera = codigos.renovar_codigo(db_session, EMAIL)

    assert (codigo, espera) == ("222222", 0)
    assert codigos.verificar_codigo(db_session, EMAIL, "222222")[0] is True


def test_codigo_gerado_tem_seis_digitos(db_session):
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(db_session, EMAIL)

    codigo, _ = codigos.renovar_codigo(db_session, EMAIL)

    assert codigo.isdigit() and len(codigo) == 6


def test_apos_intervalo_mantem_senha_e_renova_prazo_e_tentativas(db_session):
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    registro = codigo_pendente(db_session, EMAIL)
    registro.attempts = 3
    db_session.commit()
    expira_antes = registro.expires_at
    passar_intervalo_de_reenvio(db_session, EMAIL)
    enviado_antes = registro.sent_at

    codigos.renovar_codigo(db_session, EMAIL)

    registro = codigo_pendente(db_session, EMAIL)
    assert registro.password_hash == HASH_SENHA
    assert registro.attempts == 0
    assert registro.expires_at >= expira_antes
    assert registro.sent_at > enviado_antes
    assert codigos._utc(registro.sent_at) <= datetime.now(timezone.utc)


def test_novo_envio_reinicia_o_intervalo(db_session):
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(db_session, EMAIL)
    codigos.renovar_codigo(db_session, EMAIL)

    codigo, espera = codigos.renovar_codigo(db_session, EMAIL)

    assert codigo is None
    assert espera > 0


def test_codigo_antigo_deixa_de_valer_e_o_novo_cria_a_conta(db_session, monkeypatch):
    monkeypatch.setattr(codigos, "_novo_codigo", lambda: "111111")
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(db_session, EMAIL)
    monkeypatch.setattr(codigos, "_novo_codigo", lambda: "222222")
    codigos.renovar_codigo(db_session, EMAIL)

    valido_antigo, _, _ = codigos.verificar_codigo(db_session, EMAIL, "111111")
    valido_novo, _, senha = codigos.verificar_codigo(db_session, EMAIL, "222222")

    assert valido_antigo is False
    assert valido_novo is True
    assert senha == HASH_SENHA


def test_codigo_expirado_pode_ser_renovado(db_session):
    """Se o código expirou, o usuário ainda deve conseguir pedir outro."""
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    passar_intervalo_de_reenvio(db_session, EMAIL)
    registro = codigo_pendente(db_session, EMAIL)
    registro.expires_at = datetime.now(timezone.utc).replace(microsecond=0) \
        - codigos.EXPIRED_RETENTION / 2
    db_session.commit()

    codigo, _ = codigos.renovar_codigo(db_session, EMAIL)

    assert codigo is not None
    assert codigos.verificar_codigo(db_session, EMAIL, codigo)[0] is True


def test_email_e_normalizado(db_session):
    codigos.gerar_codigo(db_session, "  Ana@Exemplo.COM ", HASH_SENHA)
    passar_intervalo_de_reenvio(db_session, EMAIL)

    codigo, _ = codigos.renovar_codigo(db_session, "ANA@exemplo.com")

    assert codigo is not None
