"""Tipos de insígnia e concessão automática (INS-01 a INS-07, INS-09)."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.theme import Theme
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit

LAT, LNG = -16.6799, -49.2550


@pytest.fixture
def temas(db_session):
    arte_deco, modernismo = Theme(name="Arte Deco"), Theme(name="Modernismo")
    db_session.add_all([arte_deco, modernismo])
    db_session.commit()
    return arte_deco, modernismo


def novo_ponto(db_session, nome, temas=(), ativo=True):
    ponto = MupiObject(
        name=nome, latitude=LAT, longitude=LNG, active=ativo, themes=list(temas)
    )
    db_session.add(ponto)
    db_session.commit()
    return ponto


def nova_insignia(db_session, nome, **regra):
    insignia = Badge(name=nome, **regra)
    db_session.add(insignia)
    db_session.commit()
    return insignia


def visita(ponto):
    return BadgeRule.POINT_VISIT, {"object_id": ponto.id}


def abrir(client, ponto):
    return client.post(
        f"/mupi-objects/{ponto.id}/open", json={"latitude": LAT, "longitude": LNG}
    ).json()


def ganhas(resposta) -> list[str]:
    return sorted(b["name"] for b in resposta["awarded"])


def conquistas(db_session, usuario) -> dict[str, UserBadge]:
    db_session.expire_all()
    return {
        item.badge.name: item
        for item in db_session.query(UserBadge).filter_by(user_id=usuario.id)
    }


def visitar_direto(db_session, usuario, ponto):
    """Visita registrada antes (ex.: num ponto hoje desativado)."""
    db_session.add(UserVisit(user_id=usuario.id, object_id=ponto.id))
    db_session.commit()


# ---------- Modelo (INS-01) ----------

def test_insignia_de_visita_exige_exatamente_um_ponto(db_session):
    db_session.add(Badge(name="Sem ponto", rule_type=BadgeRule.POINT_VISIT))

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("regra", [
    {"rule_type": BadgeRule.VISIT_COUNT},                              # sem quantidade
    {"rule_type": BadgeRule.VISIT_COUNT, "required_count": 0},
    {"rule_type": BadgeRule.THEME_VISIT_COUNT, "required_count": 2},  # sem tema
])
def test_regras_inconsistentes_sao_recusadas_pelo_banco(db_session, regra):
    db_session.add(Badge(name="Errada", **regra))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_insignia_de_contagem_nao_pode_ter_ponto(db_session):
    ponto = novo_ponto(db_session, "Teatro")
    db_session.add(Badge(
        name="Errada", rule_type=BadgeRule.VISIT_COUNT, required_count=1, object_id=ponto.id
    ))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_um_ponto_pode_ter_mais_de_uma_insignia(db_session):
    ponto = novo_ponto(db_session, "Teatro")
    nova_insignia(db_session, "A", rule_type=BadgeRule.POINT_VISIT, object_id=ponto.id)
    nova_insignia(db_session, "B", rule_type=BadgeRule.POINT_VISIT, object_id=ponto.id)

    db_session.expire_all()
    assert [b.name for b in db_session.get(MupiObject, ponto.id).badges] == ["A", "B"]


def test_insignia_nova_comeca_ativa(db_session):
    insignia = nova_insignia(
        db_session, "X", rule_type=BadgeRule.VISIT_COUNT, required_count=1
    )

    assert insignia.active is True


# ---------- Visita a ponto (INS-02) ----------

def test_abrir_o_ponto_concede_a_insignia_dele(user_client, db_session, usuario):
    teatro = novo_ponto(db_session, "Teatro")
    nova_insignia(db_session, "Visitou o Teatro", rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)

    resposta = abrir(user_client, teatro)

    assert ganhas(resposta) == ["Visitou o Teatro"]
    item = conquistas(db_session, usuario)["Visitou o Teatro"]
    assert item.collected_at_object_id == teatro.id


def test_insignia_de_outro_ponto_nao_e_concedida(user_client, db_session):
    teatro, museu = novo_ponto(db_session, "Teatro"), novo_ponto(db_session, "Museu")
    nova_insignia(db_session, "Visitou o Museu", rule_type=BadgeRule.POINT_VISIT, object_id=museu.id)

    assert ganhas(abrir(user_client, teatro)) == []


def test_abrir_de_novo_nao_concede_de_novo(user_client, db_session, usuario):
    teatro = novo_ponto(db_session, "Teatro")
    nova_insignia(db_session, "Visitou o Teatro", rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)
    abrir(user_client, teatro)

    assert ganhas(abrir(user_client, teatro)) == []
    assert len(conquistas(db_session, usuario)) == 1


def test_insignia_criada_depois_vem_na_proxima_abertura(user_client, db_session, usuario):
    teatro = novo_ponto(db_session, "Teatro")
    abrir(user_client, teatro)
    nova_insignia(db_session, "Visitou o Teatro", rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)

    resposta = abrir(user_client, teatro)

    assert resposta["new_visit"] is False
    assert ganhas(resposta) == ["Visitou o Teatro"]


def test_insignia_criada_depois_vem_ao_carregar_o_perfil(user_client, db_session, usuario):
    teatro = novo_ponto(db_session, "Teatro")
    abrir(user_client, teatro)
    nova_insignia(db_session, "Visitou o Teatro", rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)

    perfil = user_client.get("/users/me").json()

    assert [b["name"] for b in perfil["badges"]] == ["Visitou o Teatro"]
    assert perfil["badges"][0]["collected_at_object"] == {"id": teatro.id, "name": "Teatro"}


# ---------- Quantidade geral e por tema (INS-03) ----------

def test_quantidade_geral_na_visita_que_completa(user_client, db_session, usuario):
    a, b = novo_ponto(db_session, "A"), novo_ponto(db_session, "B")
    nova_insignia(db_session, "Dois pontos", rule_type=BadgeRule.VISIT_COUNT, required_count=2)

    assert ganhas(abrir(user_client, a)) == []
    assert ganhas(abrir(user_client, b)) == ["Dois pontos"]
    assert conquistas(db_session, usuario)["Dois pontos"].collected_at_object_id == b.id


def test_uma_visita_conta_para_todos_os_temas_do_ponto(user_client, db_session, temas):
    arte_deco, modernismo = temas
    ponto = novo_ponto(db_session, "Edifício", temas=[arte_deco, modernismo])
    nova_insignia(db_session, "1 Arte Deco", rule_type=BadgeRule.THEME_VISIT_COUNT,
                  required_count=1, theme_id=arte_deco.id)
    nova_insignia(db_session, "1 Modernismo", rule_type=BadgeRule.THEME_VISIT_COUNT,
                  required_count=1, theme_id=modernismo.id)

    assert ganhas(abrir(user_client, ponto)) == ["1 Arte Deco", "1 Modernismo"]


def test_ponto_de_outro_tema_nao_conta(user_client, db_session, temas):
    arte_deco, modernismo = temas
    ponto = novo_ponto(db_session, "Edifício", temas=[modernismo])
    nova_insignia(db_session, "1 Arte Deco", rule_type=BadgeRule.THEME_VISIT_COUNT,
                  required_count=1, theme_id=arte_deco.id)

    assert ganhas(abrir(user_client, ponto)) == []


# ---------- Contagem não diminui (INS-05) ----------

def test_visita_a_ponto_hoje_desativado_continua_contando(user_client, db_session, usuario):
    antigo = novo_ponto(db_session, "Antigo")
    visitar_direto(db_session, usuario, antigo)
    antigo.active = False
    db_session.commit()
    novo = novo_ponto(db_session, "Novo")
    nova_insignia(db_session, "Dois pontos", rule_type=BadgeRule.VISIT_COUNT, required_count=2)

    assert ganhas(abrir(user_client, novo)) == ["Dois pontos"]


def test_insignia_ganha_fica_mesmo_se_o_ponto_perder_o_tema(user_client, db_session, usuario, temas):
    arte_deco, _ = temas
    ponto = novo_ponto(db_session, "Edifício", temas=[arte_deco])
    nova_insignia(db_session, "1 Arte Deco", rule_type=BadgeRule.THEME_VISIT_COUNT,
                  required_count=1, theme_id=arte_deco.id)
    abrir(user_client, ponto)

    ponto.themes = []
    db_session.commit()
    perfil = user_client.get("/users/me").json()

    assert [b["name"] for b in perfil["badges"]] == ["1 Arte Deco"]


# ---------- Avaliação retroativa (INS-06) ----------

def test_insignia_de_quantidade_criada_depois_vem_no_perfil(user_client, db_session, usuario):
    for nome in ("A", "B", "C"):
        abrir(user_client, novo_ponto(db_session, nome))
    nova_insignia(db_session, "Três pontos", rule_type=BadgeRule.VISIT_COUNT, required_count=3)

    perfil = user_client.get("/users/me").json()

    assert [b["name"] for b in perfil["badges"]] == ["Três pontos"]
    # Não houve um ponto: foi na avaliação retroativa
    assert perfil["badges"][0]["collected_at_object"] is None
    assert perfil["in_progress"] == []


def test_carregar_o_perfil_de_novo_nao_duplica(user_client, db_session, usuario):
    abrir(user_client, novo_ponto(db_session, "A"))
    nova_insignia(db_session, "Um ponto", rule_type=BadgeRule.VISIT_COUNT, required_count=1)

    user_client.get("/users/me")
    perfil = user_client.get("/users/me").json()

    assert perfil["badges_collected"] == 1
    assert len(conquistas(db_session, usuario)) == 1


# ---------- Insígnia desativada ----------

def test_insignia_desativada_nao_e_concedida(user_client, db_session):
    teatro = novo_ponto(db_session, "Teatro")
    insignia = nova_insignia(db_session, "Visitou o Teatro",
                             rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)
    insignia.active = False
    db_session.commit()

    resposta = abrir(user_client, teatro)

    assert ganhas(resposta) == []
    # E não aparece no conteúdo do ponto
    assert resposta["badges"] == []


def test_reativar_entrega_a_insignia_a_quem_ja_cumpria(user_client, db_session, usuario):
    teatro = novo_ponto(db_session, "Teatro")
    insignia = nova_insignia(db_session, "Visitou o Teatro",
                             rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)
    insignia.active = False
    db_session.commit()
    abrir(user_client, teatro)

    insignia.active = True
    db_session.commit()
    perfil = user_client.get("/users/me").json()

    assert [b["name"] for b in perfil["badges"]] == ["Visitou o Teatro"]


def test_desativar_depois_de_ganha_mantem_a_conquista(user_client, db_session, usuario):
    teatro = novo_ponto(db_session, "Teatro")
    insignia = nova_insignia(db_session, "Visitou o Teatro",
                             rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)
    nova_insignia(db_session, "Cinco pontos", rule_type=BadgeRule.VISIT_COUNT, required_count=5)
    abrir(user_client, teatro)

    insignia.active = False
    db_session.commit()
    perfil = user_client.get("/users/me").json()

    assert [b["name"] for b in perfil["badges"]] == ["Visitou o Teatro"]
    # Total: a ativa que falta (Cinco pontos) + a desativada que ele tem
    assert perfil["badges_total"] == 2


# ---------- Perfil ----------

def test_em_progresso_so_tem_as_de_quantidade_ativas(user_client, db_session, usuario):
    teatro = novo_ponto(db_session, "Teatro")
    nova_insignia(db_session, "Visitou o Teatro", rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)
    nova_insignia(db_session, "Cinco pontos", rule_type=BadgeRule.VISIT_COUNT, required_count=5)
    desativada = nova_insignia(db_session, "Dez pontos", rule_type=BadgeRule.VISIT_COUNT, required_count=10)
    desativada.active = False
    db_session.commit()
    visitar_direto(db_session, usuario, novo_ponto(db_session, "A"))

    perfil = user_client.get("/users/me").json()

    assert [(b["name"], b["progress"]) for b in perfil["in_progress"]] == [("Cinco pontos", 1)]
    # Total possível: as duas ativas (a desativada ninguém ganha mais)
    assert perfil["badges_total"] == 2


def test_tipo_da_insignia_vem_na_conquista(user_client, db_session):
    teatro = novo_ponto(db_session, "Teatro")
    nova_insignia(db_session, "Visitou o Teatro", rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)

    [ganha] = abrir(user_client, teatro)["awarded"]

    assert ganha["rule"]["type"] == "point_visit"
