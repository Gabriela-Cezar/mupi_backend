import pytest

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.theme import Theme
from app.model.user import User
from app.service.badge_service import register_visit

URL = "/admin/mupi-objects"


@pytest.fixture
def tema(db_session):
    tema = Theme(name="Arte Deco")
    db_session.add(tema)
    db_session.commit()
    return tema


def dados_do_ponto(**extras):
    dados = {
        "name": "Edifício Exemplo",
        "latitude": "-23.5505",
        "longitude": "-46.6333",
        "active": "true",
    }
    dados.update(extras)
    return dados


def cadastrar_ponto(client, **extras):
    return client.post(URL, data=dados_do_ponto(**extras))


def ponto_salvo(db_session, resposta):
    db_session.expire_all()
    return db_session.get(MupiObject, resposta.json()["id"])


# ---------- Gravação do tema ----------

def test_tema_informado_e_gravado_no_ponto(client, db_session, tema):
    resposta = cadastrar_ponto(client, theme_id=str(tema.id))

    assert resposta.status_code == 200
    ponto = ponto_salvo(db_session, resposta)
    assert ponto.theme_id == tema.id
    assert ponto.theme.name == "Arte Deco"


def test_tema_com_espacos_e_aceito(client, db_session, tema):
    resposta = cadastrar_ponto(client, theme_id=f"  {tema.id} ")

    assert resposta.status_code == 200
    assert ponto_salvo(db_session, resposta).theme_id == tema.id


def test_sem_tema_o_ponto_fica_sem_tema(client, db_session):
    resposta = cadastrar_ponto(client)

    assert resposta.status_code == 200
    assert ponto_salvo(db_session, resposta).theme_id is None


def test_tema_vazio_do_formulario_fica_sem_tema(client, db_session):
    """Formulários HTML mandam "" quando nenhum tema é selecionado."""
    resposta = cadastrar_ponto(client, theme_id="")

    assert resposta.status_code == 200
    assert ponto_salvo(db_session, resposta).theme_id is None


# ---------- Validação ----------

def test_tema_inexistente_retorna_400_e_nao_cria_ponto(client, db_session):
    resposta = cadastrar_ponto(client, theme_id="999")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Tema não encontrado."
    assert db_session.query(MupiObject).count() == 0


def test_tema_nao_numerico_retorna_400_e_nao_cria_ponto(client, db_session):
    resposta = cadastrar_ponto(client, theme_id="abc")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Valor inválido para tema."
    assert db_session.query(MupiObject).count() == 0


# ---------- Efeito nas insígnias ----------

def test_insignia_por_tema_passa_a_ser_concedida(client, db_session, tema):
    """Era o impacto da falha: sem tema gravado, a insígnia nunca era ganha."""
    insignia = Badge(
        name="Visitar 1 ponto Arte Deco",
        rule_type=BadgeRule.THEME_VISIT_COUNT,
        required_count=1,
        theme_id=tema.id,
    )
    usuario = User(email="ana@exemplo.com", password_hash="hash")
    db_session.add_all([insignia, usuario])
    db_session.commit()

    resposta = cadastrar_ponto(client, theme_id=str(tema.id))
    ponto = ponto_salvo(db_session, resposta)

    nova_visita, ganhas = register_visit(db_session, usuario.id, ponto)

    assert nova_visita is True
    assert [g.badge_id for g in ganhas] == [insignia.id]


def test_ponto_de_outro_tema_nao_concede_a_insignia(client, db_session, tema):
    outro_tema = Theme(name="Modernismo")
    insignia = Badge(
        name="Visitar 1 ponto Arte Deco",
        rule_type=BadgeRule.THEME_VISIT_COUNT,
        required_count=1,
        theme_id=tema.id,
    )
    usuario = User(email="ana@exemplo.com", password_hash="hash")
    db_session.add_all([outro_tema, insignia, usuario])
    db_session.commit()

    resposta = cadastrar_ponto(client, theme_id=str(outro_tema.id))
    ponto = ponto_salvo(db_session, resposta)

    _, ganhas = register_visit(db_session, usuario.id, ponto)

    assert ganhas == []
