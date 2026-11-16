"""Mensagens de sucesso do painel (ADM-12).

Depois de salvar, o painel redireciona para a lista com `?msg=<código>`.
Só os códigos daqui são exibidos: o texto nunca vem da URL.
"""
from urllib.parse import urlencode

MESSAGES = {
    "point-created": "Ponto cadastrado.",
    "point-updated": "Ponto atualizado.",
    "point-activated": "Ponto ativado: ele volta a aparecer no app.",
    "point-deactivated": "Ponto desativado: ele não aparece mais no app. O histórico foi mantido.",
    "point-deleted": "Ponto excluído.",
    "theme-created": "Tema cadastrado.",
    "theme-updated": "Tema atualizado.",
    "theme-deleted": "Tema excluído.",
}


def with_message(path: str, code: str) -> str:
    """Endereço da página com a mensagem de sucesso."""
    assert code in MESSAGES, code
    return f"{path}?{urlencode({'msg': code})}"


def message_for(code: str | None) -> str | None:
    return MESSAGES.get(code or "")
