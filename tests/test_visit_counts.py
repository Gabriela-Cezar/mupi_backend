"""Contagem de visitas não diminui quando um ponto é desativado (FAL-12)."""
import pytest

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.theme import Theme
from app.model.user import User
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit
from app.service.badge_service import register_visit, visit_counts

LAT, LNG = -16.6857, -49.2462
PERTO = {"latitude": LAT, "longitude": LNG}


@pytest.fixture
def arte_deco(db_session):
    tema = Theme(name="Arte Deco")
    db_session.add(tema)
    db_session.commit()
    return tema


def criar_ponto(db_session, nome, tema=None, ativo=True, lat=LAT, lng=LNG):
    ponto = MupiObject(
        name=nome,
        latitude=lat,
        longitude=lng,
        active=ativo,
        theme_id=tema.id if tema else None,
    )
    db_session.add(ponto)
    db_session.commit()
    return ponto


def visitar(db_session, usuario, *pontos):
    for ponto in pontos:
        db_session.add(UserVisit(user_id=usuario.id, object_id=ponto.id))
    db_session.commit()


def desativar(db_session, ponto):
    ponto.active = False
    db_session.commit()


def criar_insignia(db_session, nome, regra, quantidade, tema=None):
    insignia = Badge(
        name=nome,
        rule_type=regra,
        required_count=quantidade,
        theme_id=tema.id if tema else None,
    )
    db_session.add(insignia)
    db_session.commit()
    return insignia


# ---------- visit_counts ----------

def test_sem_visitas(db_session, usuario):
    assert visit_counts(db_session, usuario.id) == (0, {})


def test_visita_a_ponto_desativado_continua_contando(db_session, usuario, arte_deco):
    a = criar_ponto(db_session, "A", arte_deco)
    b = criar_ponto(db_session, "B", arte_deco)
    visitar(db_session, usuario, a, b)

    desativar(db_session, a)

    assert visit_counts(db_session, usuario.id) == (2, {arte_deco.id: 2})


def test_ponto_sem_tema_conta_so_no_total(db_session, usuario, arte_deco):
    com_tema = criar_ponto(db_session, "Com tema", arte_deco)
    sem_tema = criar_ponto(db_session, "Sem tema")
    visitar(db_session, usuario, com_tema, sem_tema)

    assert visit_counts(db_session, usuario.id) == (2, {arte_deco.id: 1})


def test_visitas_de_outro_usuario_nao_contam(db_session, usuario, arte_deco):
    outro = User(email="outro@exemplo.com", password_hash="x")
    db_session.add(outro)
    db_session.commit()
    a = criar_ponto(db_session, "A", arte_deco)
    visitar(db_session, outro, a)

    assert visit_counts(db_session, usuario.id) == (0, {})


def test_varios_temas(db_session, usuario, arte_deco):
    modernismo = Theme(name="Modernismo")
    db_session.add(modernismo)
    db_session.commit()
    pontos = [
        criar_ponto(db_session, "A", arte_deco),
        criar_ponto(db_session, "B", arte_deco, ativo=False),
        criar_ponto(db_session, "C", modernismo),
    ]
    visitar(db_session, usuario, *pontos)

    assert visit_counts(db_session, usuario.id) == (
        3, {arte_deco.id: 2, modernismo.id: 1},
    )


# ---------- Concessão de insígnias ----------

def test_insignia_de_contagem_considera_ponto_desativado(db_session, usuario):
    insignia = criar_insignia(db_session, "Visitar 2 pontos", BadgeRule.VISIT_COUNT, 2)
    a = criar_ponto(db_session, "A")
    b = criar_ponto(db_session, "B")
    visitar(db_session, usuario, a)
    desativar(db_session, a)

    _, ganhas = register_visit(db_session, usuario.id, b)

    assert [g.badge_id for g in ganhas] == [insignia.id]


def test_insignia_por_tema_considera_ponto_desativado(db_session, usuario, arte_deco):
    insignia = criar_insignia(
        db_session, "2 pontos Arte Deco", BadgeRule.THEME_VISIT_COUNT, 2, arte_deco,
    )
    a = criar_ponto(db_session, "A", arte_deco)
    b = criar_ponto(db_session, "B", arte_deco)
    visitar(db_session, usuario, a)
    desativar(db_session, a)

    _, ganhas = register_visit(db_session, usuario.id, b)

    assert [g.badge_id for g in ganhas] == [insignia.id]


def test_insignia_ja_ganha_continua_depois_de_desativar(db_session, usuario):
    insignia = criar_insignia(db_session, "Visitar 1 ponto", BadgeRule.VISIT_COUNT, 1)
    a = criar_ponto(db_session, "A")
    register_visit(db_session, usuario.id, a)
    db_session.commit()

    desativar(db_session, a)

    assert db_session.get(UserBadge, (usuario.id, insignia.id)) is not None


# ---------- O que o usuário vê no app ----------

def test_perfil_nao_perde_visitas_nem_progresso(user_client, db_session, usuario, arte_deco):
    criar_insignia(db_session, "3 pontos Arte Deco", BadgeRule.THEME_VISIT_COUNT, 3, arte_deco)
    a = criar_ponto(db_session, "A", arte_deco)
    b = criar_ponto(db_session, "B", arte_deco)
    visitar(db_session, usuario, a, b)

    antes = user_client.get("/users/me").json()
    desativar(db_session, a)
    depois = user_client.get("/users/me").json()

    assert antes["visits_total"] == depois["visits_total"] == 2
    assert [i["progress"] for i in depois["in_progress"]] == [2]
    assert [i["progress"] for i in antes["in_progress"]] == [2]


def test_abrir_ponto_conta_visitas_a_pontos_desativados(user_client, db_session, usuario):
    antigo = criar_ponto(db_session, "Antigo", lat=LAT + 0.01)
    visitar(db_session, usuario, antigo)
    desativar(db_session, antigo)
    novo = criar_ponto(db_session, "Novo")

    resposta = user_client.post(f"/mupi-objects/{novo.id}/open", json=PERTO)

    assert resposta.status_code == 200
    assert resposta.json()["visits_total"] == 2


def test_abrir_ponto_concede_insignia_contando_ponto_desativado(user_client, db_session, usuario):
    criar_insignia(db_session, "Visitar 2 pontos", BadgeRule.VISIT_COUNT, 2)
    antigo = criar_ponto(db_session, "Antigo", lat=LAT + 0.01)
    visitar(db_session, usuario, antigo)
    desativar(db_session, antigo)
    novo = criar_ponto(db_session, "Novo")

    resposta = user_client.post(f"/mupi-objects/{novo.id}/open", json=PERTO)

    assert [i["name"] for i in resposta.json()["awarded"]] == ["Visitar 2 pontos"]
