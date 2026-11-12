"""Códigos de 6 dígitos enviados por e-mail: cadastro e recuperação de senha.

Ficam no banco (tabela email_codes), e não na memória (FAL-13): sobrevivem
a reinícios do servidor e valem em qualquer processo. Só o hash do código é
guardado. Todas as funções confirmam (commit) o que alteram.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import SECRET_KEY
from app.model.email_code import EmailCode

CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60

# Um código de cadastro expirado ainda pode ser reenviado (a senha escolhida
# continua guardada); depois deste prazo o registro é apagado e a pessoa
# precisa refazer o cadastro.
EXPIRED_RETENTION = timedelta(days=1)

VERIFICACAO = "verificacao"
RECUPERACAO = "recuperacao"


def _chave(email: str) -> str:
    return email.strip().lower()


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _utc(momento: datetime) -> datetime:
    # O SQLite (testes) devolve as datas sem fuso; o PostgreSQL, com fuso
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento


def _novo_codigo() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash(codigo: str, email: str, finalidade: str) -> str:
    # HMAC com a SECRET_KEY: com só 1 milhão de códigos possíveis, um hash
    # comum seria descoberto na hora por quem visse o banco
    mensagem = f"{finalidade}:{email}:{codigo}".encode()
    return hmac.new(SECRET_KEY.encode(), mensagem, hashlib.sha256).hexdigest()


def _buscar(db: Session, email: str, finalidade: str, travar=False) -> EmailCode | None:
    consulta = select(EmailCode).where(
        EmailCode.email == email,
        EmailCode.purpose == finalidade,
    )

    if travar:
        # Duas verificações simultâneas não podem usar o mesmo código
        consulta = consulta.with_for_update()

    return db.scalars(consulta).first()


def apagar_expirados(db: Session) -> int:
    """Apaga os códigos vencidos há mais de EXPIRED_RETENTION. Não faz commit."""
    limite = _agora() - EXPIRED_RETENTION
    resultado = db.execute(
        delete(EmailCode).where(EmailCode.expires_at < limite),
        # "fetch": tira da sessão os registros apagados, sem comparar datas em
        # Python (o SQLite devolve datas sem fuso)
        execution_options={"synchronize_session": "fetch"},
    )
    return resultado.rowcount


def _salvar_novo(
    db: Session,
    email: str,
    finalidade: str,
    password_hash: str | None = None,
) -> str:
    """Cria o código (ou substitui o anterior do mesmo e-mail e finalidade)."""
    apagar_expirados(db)

    codigo = _novo_codigo()
    agora = _agora()
    registro = _buscar(db, email, finalidade, travar=True)

    if registro is None:
        registro = EmailCode(email=email, purpose=finalidade)
        db.add(registro)

    registro.code_hash = _hash(codigo, email, finalidade)
    registro.password_hash = password_hash
    registro.expires_at = agora + timedelta(minutes=CODE_TTL_MINUTES)
    registro.attempts = 0
    registro.sent_at = agora

    db.commit()
    return codigo


def _validar(
    db: Session,
    email: str,
    codigo_digitado: str,
    finalidade: str,
    nome: str,
) -> tuple[bool, str, EmailCode | None]:
    registro = _buscar(db, email, finalidade, travar=True)

    if registro is None:
        db.rollback()
        return False, f"Nenhum código de {nome} encontrado.", None

    if _agora() > _utc(registro.expires_at):
        db.delete(registro)
        db.commit()
        return False, f"O código de {nome} expirou.", None

    codigo_correto = hmac.compare_digest(
        _hash(codigo_digitado, email, finalidade),
        registro.code_hash,
    )

    if not codigo_correto:
        registro.attempts += 1

        if registro.attempts >= MAX_ATTEMPTS:
            db.delete(registro)
            db.commit()
            return (
                False,
                "Número máximo de tentativas excedido. Solicite um novo código.",
                None,
            )

        db.commit()
        return False, f"Código de {nome} inválido.", None

    # Uso único
    db.delete(registro)
    db.commit()

    return True, "", registro


# ---------- Cadastro ----------

def gerar_codigo(db: Session, email: str, hashed_password: str) -> str:
    return _salvar_novo(db, _chave(email), VERIFICACAO, hashed_password)


def renovar_codigo(db: Session, email: str) -> tuple[str | None, int]:
    """Gera um novo código para um cadastro pendente, mantendo a senha.

    Retorna (codigo, 0) em caso de sucesso, (None, segundos) se ainda está
    no intervalo mínimo entre envios, ou (None, 0) se não há cadastro pendente.
    """
    registro = _buscar(db, _chave(email), VERIFICACAO)

    if registro is None:
        return None, 0

    passados = (_agora() - _utc(registro.sent_at)).total_seconds()
    espera = RESEND_COOLDOWN_SECONDS - passados

    if espera > 0:
        return None, int(espera) + 1

    return _salvar_novo(db, registro.email, VERIFICACAO, registro.password_hash), 0


def verificar_codigo(
    db: Session,
    email: str,
    codigo_digitado: str,
) -> tuple[bool, str, str | None]:
    valido, mensagem, registro = _validar(
        db, _chave(email), codigo_digitado, VERIFICACAO, "verificação"
    )

    if not valido:
        return False, mensagem, None

    return True, "E-mail verificado com sucesso.", registro.password_hash


# ---------- Recuperação de senha ----------

def gerar_codigo_recuperacao(db: Session, email: str) -> str:
    return _salvar_novo(db, _chave(email), RECUPERACAO)


def verificar_codigo_recuperacao(
    db: Session,
    email: str,
    codigo_digitado: str,
) -> tuple[bool, str]:
    valido, mensagem, _ = _validar(
        db, _chave(email), codigo_digitado, RECUPERACAO, "recuperação"
    )

    if not valido:
        return False, mensagem

    return True, "Código de recuperação validado com sucesso."
