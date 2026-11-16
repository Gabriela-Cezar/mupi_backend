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
    "badge-created": "Insígnia cadastrada.",
    "badge-updated": "Insígnia atualizada.",
    "badge-activated": "Insígnia ativada: ela volta a ser concedida.",
    "badge-deactivated": "Insígnia desativada: ela deixa de ser concedida. Quem já tem continua com ela.",
    "badge-deleted": "Insígnia excluída.",
    "route-created": "Rota cadastrada.",
    "route-updated": "Rota atualizada.",
    "route-saved-path-error": "Rota salva, mas o trajeto não pôde ser calculado. A rota fica desativada: veja o erro abaixo e recalcule o trajeto.",
    "route-saved-inactive": "Rota salva, mas ainda não pode ser ativada: veja o que falta abaixo.",
    "route-path-updated": "Trajeto recalculado.",
    "route-path-error": "O trajeto não pôde ser calculado: veja o erro abaixo.",
    "route-activated": "Rota ativada: ela aparece no app.",
    "route-deactivated": "Rota desativada: ela não aparece mais no app.",
    "route-deleted": "Rota excluída.",
    "point-deactivated-routes": "Ponto desativado. As rotas que passam por ele também foram desativadas, até serem corrigidas.",
    "point-updated-routes": "Ponto atualizado. Como ele foi desativado, as rotas que passam por ele também foram desativadas.",
}


def with_message(path: str, code: str) -> str:
    """Endereço da página com a mensagem de sucesso."""
    assert code in MESSAGES, code
    return f"{path}?{urlencode({'msg': code})}"


def message_for(code: str | None) -> str | None:
    return MESSAGES.get(code or "")
