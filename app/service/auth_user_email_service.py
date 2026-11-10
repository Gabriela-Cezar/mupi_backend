import secrets
from datetime import datetime, timedelta, timezone

CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5

codigos_verificacao: dict[str, dict] = {}
codigos_recuperacao: dict[str, dict] = {}


def _chave(email: str) -> str:
    return email.strip().lower()


def _novo_codigo() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _expira_em() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)


def _validar(
    store: dict,
    email: str,
    codigo_digitado: str,
    nome: str
) -> tuple[bool, str, dict | None]:
    dados = store.get(email)

    if dados is None:
        return False, f"Nenhum código de {nome} encontrado.", None

    if datetime.now(timezone.utc) > dados["expira_em"]:
        del store[email]
        return False, f"O código de {nome} expirou.", None

    codigo_correto = secrets.compare_digest(
        codigo_digitado.encode(),
        dados["codigo"].encode()
    )

    if not codigo_correto:
        dados["tentativas"] += 1

        if dados["tentativas"] >= MAX_ATTEMPTS:
            del store[email]
            return (
                False,
                "Número máximo de tentativas excedido. Solicite um novo código.",
                None
            )

        return False, f"Código de {nome} inválido.", None

    del store[email] 

    return True, "", dados


RESEND_COOLDOWN_SECONDS = 60


def gerar_codigo(email: str, hashed_password: str) -> str:
    codigo = _novo_codigo()

    codigos_verificacao[_chave(email)] = {
        "codigo": codigo,
        "password_hash": hashed_password,
        "expira_em": _expira_em(),
        "tentativas": 0,
        "enviado_em": datetime.now(timezone.utc),
    }

    return codigo


def renovar_codigo(email: str) -> tuple[str | None, int]:
    """Gera um novo código para um cadastro pendente, mantendo a senha.

    Retorna (codigo, 0) em caso de sucesso, (None, segundos) se ainda está
    no intervalo mínimo entre envios, ou (None, 0) se não há cadastro pendente.
    """
    dados = codigos_verificacao.get(_chave(email))

    if dados is None:
        return None, 0

    agora = datetime.now(timezone.utc)
    espera = RESEND_COOLDOWN_SECONDS - (agora - dados["enviado_em"]).total_seconds()

    if espera > 0:
        return None, int(espera) + 1

    codigo = _novo_codigo()

    dados.update(
        codigo=codigo,
        expira_em=_expira_em(),
        tentativas=0,
        enviado_em=agora,
    )

    return codigo, 0


def verificar_codigo(
    email: str,
    codigo_digitado: str
) -> tuple[bool, str, str | None]:
    valido, mensagem, dados = _validar(
        codigos_verificacao,
        _chave(email),
        codigo_digitado,
        "verificação"
    )

    if not valido:
        return False, mensagem, None

    return True, "E-mail verificado com sucesso.", dados["password_hash"]


def gerar_codigo_recuperacao(email: str) -> str:
    codigo = _novo_codigo()

    codigos_recuperacao[_chave(email)] = {
        "codigo": codigo,
        "expira_em": _expira_em(),
        "tentativas": 0,
    }

    return codigo


def verificar_codigo_recuperacao(
    email: str,
    codigo_digitado: str
) -> tuple[bool, str]:
    valido, mensagem, _ = _validar(
        codigos_recuperacao,
        _chave(email),
        codigo_digitado,
        "recuperação"
    )

    if not valido:
        return False, mensagem

    return True, "Código de recuperação validado com sucesso."