"""Códigos de verificação e recuperação guardados no banco (FAL-13 / USR-09)."""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.all_models import Base
from app.model.email_code import EmailCode
from app.model.user import User
from app.service import auth_user_email_service as codigos
from app.service.auth_service import gerar_password_hash
from tests.conftest import codigo_do_ultimo_email, codigo_pendente, passar_intervalo_de_reenvio

EMAIL = "ana@exemplo.com"
SENHA = "senha-segura-123"
HASH_SENHA = "hash-da-senha"


def todos(db):
    return db.query(EmailCode).all()


def vencer(db, email, finalidade="verificacao", ha=timedelta(minutes=1)):
    registro = codigo_pendente(db, email, finalidade)
    registro.expires_at = datetime.now(timezone.utc) - ha
    db.commit()


# ---------- O código não fica em texto puro ----------

def test_codigo_nao_e_guardado_em_texto_puro(db_session):
    codigo = codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)

    registro = codigo_pendente(db_session, EMAIL)
    colunas = [str(getattr(registro, c.name)) for c in EmailCode.__table__.columns]
    assert not any(codigo in valor for valor in colunas)


def test_hash_usa_a_chave_secreta(db_session):
    """Um SHA-256 simples do código seria descoberto testando 1 milhão de valores."""
    codigo = codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)

    registro = codigo_pendente(db_session, EMAIL)
    assert registro.code_hash != hashlib.sha256(codigo.encode()).hexdigest()
    assert len(registro.code_hash) == 64


def test_mesmo_codigo_em_emails_diferentes_tem_hash_diferente(db_session, monkeypatch):
    monkeypatch.setattr(codigos, "_novo_codigo", lambda: "123456")
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    codigos.gerar_codigo(db_session, "beto@exemplo.com", HASH_SENHA)

    hashes = {r.code_hash for r in todos(db_session)}
    assert len(hashes) == 2


# ---------- Sobrevive a reinícios e vale em qualquer processo ----------

@pytest.fixture
def dois_processos(tmp_path):
    """Duas conexões independentes ao mesmo banco, como dois processos."""
    url = f"sqlite:///{tmp_path / 'codigos.db'}"
    engines = [create_engine(url), create_engine(url)]
    Base.metadata.create_all(engines[0])
    sessoes = [Session(e) for e in engines]
    yield sessoes
    for sessao, engine in zip(sessoes, engines):
        sessao.close()
        engine.dispose()


def test_codigo_gerado_em_um_processo_vale_no_outro(dois_processos):
    processo_a, processo_b = dois_processos

    codigo = codigos.gerar_codigo(processo_a, EMAIL, HASH_SENHA)

    valido, _, senha = codigos.verificar_codigo(processo_b, EMAIL, codigo)
    assert valido is True
    assert senha == HASH_SENHA


def test_codigo_continua_valendo_depois_de_reiniciar(tmp_path):
    url = f"sqlite:///{tmp_path / 'reinicio.db'}"
    antes = create_engine(url)
    Base.metadata.create_all(antes)
    with Session(antes) as db:
        codigo = codigos.gerar_codigo_recuperacao(db, EMAIL)
    antes.dispose()  # "servidor desligado"

    depois = create_engine(url)
    with Session(depois) as db:
        valido, _ = codigos.verificar_codigo_recuperacao(db, EMAIL, codigo)
    depois.dispose()

    assert valido is True


def test_tentativas_erradas_somam_entre_processos(dois_processos):
    processo_a, processo_b = dois_processos
    codigo = codigos.gerar_codigo(processo_a, EMAIL, HASH_SENHA)
    errado = "000000" if codigo != "000000" else "111111"

    for i in range(codigos.MAX_ATTEMPTS):
        sessao = (processo_a, processo_b)[i % 2]
        codigos.verificar_codigo(sessao, EMAIL, errado)

    # Esgotou as 5 tentativas: nem o código certo vale mais
    assert codigos.verificar_codigo(processo_a, EMAIL, codigo)[0] is False


# ---------- Regras mantidas ----------

def test_um_codigo_por_email_e_finalidade(db_session):
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    codigos.gerar_codigo(db_session, EMAIL, "outra-senha")
    codigos.gerar_codigo_recuperacao(db_session, EMAIL)

    finalidades = sorted(r.purpose for r in todos(db_session))
    assert finalidades == ["recuperacao", "verificacao"]
    assert codigo_pendente(db_session, EMAIL).password_hash == "outra-senha"


def test_novo_cadastro_invalida_o_codigo_anterior(db_session):
    primeiro = codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    segundo = codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)

    if primeiro != segundo:  # chance de 1 em 1 milhão de serem iguais
        assert codigos.verificar_codigo(db_session, EMAIL, primeiro)[0] is False
    assert codigos.verificar_codigo(db_session, EMAIL, segundo)[0] is True


def test_banco_recusa_dois_codigos_para_o_mesmo_email_e_finalidade(db_session):
    agora = datetime.now(timezone.utc)
    for _ in range(2):
        db_session.add(EmailCode(
            email=EMAIL, purpose="verificacao", code_hash="x" * 64,
            expires_at=agora, sent_at=agora,
        ))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_banco_recusa_finalidade_desconhecida(db_session):
    agora = datetime.now(timezone.utc)
    db_session.add(EmailCode(
        email=EMAIL, purpose="outra", code_hash="x" * 64,
        expires_at=agora, sent_at=agora,
    ))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_codigo_de_recuperacao_nao_serve_para_verificar_cadastro(db_session, monkeypatch):
    monkeypatch.setattr(codigos, "_novo_codigo", lambda: "123456")
    codigos.gerar_codigo_recuperacao(db_session, EMAIL)

    valido, mensagem, _ = codigos.verificar_codigo(db_session, EMAIL, "123456")

    assert valido is False
    assert mensagem == "Nenhum código de verificação encontrado."


def test_codigo_vale_uma_vez_so(db_session):
    codigo = codigos.gerar_codigo_recuperacao(db_session, EMAIL)

    primeira = codigos.verificar_codigo_recuperacao(db_session, EMAIL, codigo)
    segunda = codigos.verificar_codigo_recuperacao(db_session, EMAIL, codigo)

    assert primeira[0] is True
    assert segunda == (False, "Nenhum código de recuperação encontrado.")
    assert todos(db_session) == []


def test_codigo_vale_10_minutos(db_session):
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)

    registro = codigo_pendente(db_session, EMAIL)
    duracao = codigos._utc(registro.expires_at) - codigos._utc(registro.sent_at)
    assert duracao == timedelta(minutes=codigos.CODE_TTL_MINUTES)


def test_codigo_expirado_e_recusado(db_session):
    codigo = codigos.gerar_codigo_recuperacao(db_session, EMAIL)
    vencer(db_session, EMAIL, "recuperacao")

    assert codigos.verificar_codigo_recuperacao(db_session, EMAIL, codigo) == (
        False, "O código de recuperação expirou.",
    )
    assert todos(db_session) == []


def test_tentativa_errada_fica_registrada(db_session):
    codigo = codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    errado = "000000" if codigo != "000000" else "111111"

    valido, mensagem, _ = codigos.verificar_codigo(db_session, EMAIL, errado)

    assert (valido, mensagem) == (False, "Código de verificação inválido.")
    assert codigo_pendente(db_session, EMAIL).attempts == 1


def test_quinta_tentativa_errada_apaga_o_codigo(db_session):
    codigo = codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    errado = "000000" if codigo != "000000" else "111111"

    for _ in range(codigos.MAX_ATTEMPTS - 1):
        codigos.verificar_codigo(db_session, EMAIL, errado)
    _, mensagem, _ = codigos.verificar_codigo(db_session, EMAIL, errado)

    assert mensagem.startswith("Número máximo de tentativas excedido")
    assert codigo_pendente(db_session, EMAIL) is None


# ---------- Limpeza dos códigos vencidos ----------

def test_gerar_codigo_apaga_os_vencidos_ha_mais_de_um_dia(db_session):
    codigos.gerar_codigo(db_session, "antigo@exemplo.com", HASH_SENHA)
    vencer(db_session, "antigo@exemplo.com", ha=codigos.EXPIRED_RETENTION + timedelta(minutes=1))
    codigos.gerar_codigo(db_session, "recente@exemplo.com", HASH_SENHA)
    vencer(db_session, "recente@exemplo.com", ha=timedelta(hours=1))

    codigos.gerar_codigo_recuperacao(db_session, EMAIL)

    emails = sorted(r.email for r in todos(db_session))
    assert emails == [EMAIL, "recente@exemplo.com"]


def test_cadastro_vencido_ha_pouco_ainda_pode_pedir_reenvio(db_session):
    """O código venceu, mas a senha escolhida continua guardada por um dia."""
    codigos.gerar_codigo(db_session, EMAIL, HASH_SENHA)
    vencer(db_session, EMAIL, ha=timedelta(hours=2))
    passar_intervalo_de_reenvio(db_session, EMAIL)
    codigos.gerar_codigo_recuperacao(db_session, "outro@exemplo.com")  # dispara a limpeza

    codigo, _ = codigos.renovar_codigo(db_session, EMAIL)

    assert codigos.verificar_codigo(db_session, EMAIL, codigo)[2] == HASH_SENHA


# ---------- Pela API ----------

def test_cadastro_completo_pela_api(client, db_session, emails_enviados):
    client.post("/auth/register", json={"email": EMAIL, "password": SENHA})
    codigo = codigo_do_ultimo_email(emails_enviados)

    resposta = client.post("/auth/verify-email", json={"email": EMAIL, "codigo": codigo})

    assert resposta.status_code == 200
    assert db_session.query(User).filter_by(email=EMAIL).count() == 1
    assert todos(db_session) == []


def test_cadastro_guarda_o_hash_da_senha_e_nao_a_senha(client, db_session, emails_enviados):
    client.post("/auth/register", json={"email": EMAIL, "password": SENHA})

    registro = codigo_pendente(db_session, EMAIL)
    assert registro.password_hash and SENHA not in registro.password_hash


def test_recuperacao_completa_pela_api(client, db_session, emails_enviados):
    db_session.add(User(email=EMAIL, password_hash=gerar_password_hash(SENHA), email_verified=True))
    db_session.commit()
    client.post("/auth/recovery-password", json={"email": EMAIL})
    codigo = codigo_do_ultimo_email(emails_enviados)

    resposta = client.post("/auth/verify-recovery-code", json={"email": EMAIL, "codigo": codigo})

    assert resposta.status_code == 200
    assert "reset_token" in resposta.json()
    assert codigo_pendente(db_session, EMAIL, "recuperacao") is None


def test_recuperacao_para_email_sem_conta_nao_gera_codigo(client, db_session, emails_enviados):
    client.post("/auth/recovery-password", json={"email": EMAIL})

    assert todos(db_session) == []
    assert emails_enviados == []
