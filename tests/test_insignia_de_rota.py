"""Insígnia de conclusão de rota (INS-04, INS-07) e eventos de rota (ADM-10)."""
import html

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.route import AgeRating, Route, RouteDifficulty, RoutePoint
from app.model.route_event import RouteEvent
from app.model.user_badge import UserBadge
from tests.test_migrations import alembic_cfg


@pytest.fixture
def pontos(db_session):
    lista = [
        MupiObject(name=nome, latitude=-16.68 - i / 100, longitude=-49.25)
        for i, nome in enumerate(["A", "B"])
    ]
    db_session.add_all(lista)
    db_session.commit()
    return lista


def nova_rota(db_session, nome, pontos_):
    route = Route(
        name=nome, difficulty=RouteDifficulty.EASY, age_rating=AgeRating.FREE, active=True,
        cover_key="routes/x/cover.png",
        path=[[p.longitude, p.latitude] for p in pontos_], waypoints=list(range(len(pontos_))),
        distance_m=1000, walk_seconds=600,
        points=[RoutePoint(object_id=p.id, position=i, mupi_object=p) for i, p in enumerate(pontos_)],
    )
    db_session.add(route)
    db_session.commit()
    return route


@pytest.fixture
def rota(db_session, pontos):
    return nova_rota(db_session, "Centro", pontos)


def insignia_da_rota(db_session, route, nome="Concluiu o Centro", **extras):
    badge = Badge(name=nome, rule_type=BadgeRule.ROUTE_COMPLETION, route_id=route.id, **extras)
    db_session.add(badge)
    db_session.commit()
    return badge


def fazer_a_rota(client, route, pontos_):
    client.post(f"/routes/{route.id}/start")
    for ponto in pontos_:
        posicao = {"latitude": ponto.latitude, "longitude": ponto.longitude}
        assert client.post(f"/mupi-objects/{ponto.id}/open", json=posicao).status_code == 200
        assert client.post(
            f"/users/me/active-route/points/{ponto.id}/finish", json=posicao
        ).status_code == 200
    return client.post("/users/me/active-route/complete").json()


def eventos(db_session):
    db_session.expire_all()
    return [e.kind for e in db_session.query(RouteEvent).order_by(RouteEvent.id)]


# ---------- Modelo ----------

def test_insignia_de_rota_exige_a_rota(db_session):
    db_session.add(Badge(name="Sem rota", rule_type=BadgeRule.ROUTE_COMPLETION))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_uma_insignia_de_conclusao_por_rota(db_session, rota):
    insignia_da_rota(db_session, rota)
    db_session.add(Badge(name="Outra", rule_type=BadgeRule.ROUTE_COMPLETION, route_id=rota.id))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_outros_tipos_nao_podem_ter_rota(db_session, rota):
    db_session.add(Badge(
        name="Errada", rule_type=BadgeRule.VISIT_COUNT, required_count=1, route_id=rota.id,
    ))

    with pytest.raises(IntegrityError):
        db_session.commit()


# ---------- Concessão (INS-04) ----------

def test_encerrar_a_rota_concede_a_insignia(user_client, db_session, usuario, rota, pontos):
    insignia_da_rota(db_session, rota)

    resposta = fazer_a_rota(user_client, rota, pontos)

    [ganha] = [b for b in resposta["awarded"] if b["name"] == "Concluiu o Centro"]
    assert ganha["rule"]["type"] == "route_completion"
    assert ganha["collected_at_route"] == {"id": rota.id, "name": "Centro"}
    assert ganha["collected_at_object"] is None


def test_refazer_a_rota_nao_concede_de_novo(user_client, db_session, usuario, rota, pontos):
    insignia_da_rota(db_session, rota)
    fazer_a_rota(user_client, rota, pontos)

    resposta = fazer_a_rota(user_client, rota, pontos)

    assert resposta["completions"] == 2
    assert resposta["awarded"] == []
    db_session.expire_all()
    assert db_session.query(UserBadge).filter_by(user_id=usuario.id).count() == 1


def test_insignia_de_outra_rota_nao_e_concedida(user_client, db_session, rota, pontos):
    outra = nova_rota(db_session, "Arte", pontos)
    insignia_da_rota(db_session, outra)

    assert fazer_a_rota(user_client, rota, pontos)["awarded"] == []


def test_insignia_criada_depois_vem_no_perfil(user_client, db_session, rota, pontos):
    fazer_a_rota(user_client, rota, pontos)
    insignia_da_rota(db_session, rota)

    perfil = user_client.get("/users/me").json()

    [ganha] = perfil["badges"]
    assert ganha["name"] == "Concluiu o Centro"
    assert ganha["collected_at_route"]["name"] == "Centro"


def test_insignia_desativada_nao_e_concedida(user_client, db_session, rota, pontos):
    insignia_da_rota(db_session, rota, active=False)

    assert fazer_a_rota(user_client, rota, pontos)["awarded"] == []


def test_abandonar_nao_concede(user_client, db_session, usuario, rota, pontos):
    insignia_da_rota(db_session, rota)
    user_client.post(f"/routes/{rota.id}/start")
    user_client.delete("/users/me/active-route")

    user_client.get("/users/me")

    db_session.expire_all()
    assert db_session.query(UserBadge).filter_by(user_id=usuario.id).count() == 0


def test_perfil_mostra_a_insignia_de_rota_bloqueada_sem_revelar_a_rota(user_client, db_session, rota):
    badge = insignia_da_rota(db_session, rota)

    perfil = user_client.get("/users/me").json()

    assert perfil["locked"] == [{"id": badge.id, "type": "route_completion"}]
    assert perfil["in_progress"] == []
    assert perfil["badges_total"] == 1


# ---------- Painel ----------

def criar_no_painel(admin_client, **campos):
    dados = {"name": "Concluiu o Centro", "active": "true", "rule_type": "route_completion", **campos}
    return admin_client.post("/admin/badges", data=dados, follow_redirects=False)


def test_painel_cria_insignia_de_rota(admin_client, db_session, rota):
    resposta = criar_no_painel(admin_client, route_id=str(rota.id))

    assert resposta.status_code == 303
    db_session.expire_all()
    badge = db_session.query(Badge).one()
    assert (badge.rule_type, badge.route_id) == (BadgeRule.ROUTE_COMPLETION, rota.id)

    lista = html.unescape(admin_client.get("/admin/badges").text)
    assert "Conclusão de rota" in lista
    assert "Concluir a rota Centro" in lista


def test_formulario_tem_o_tipo_e_as_rotas(admin_client, rota):
    pagina = admin_client.get("/admin/badges/new").text

    assert 'value="route_completion"' in pagina
    assert 'name="route_id"' in pagina
    assert f'value="{rota.id}"' in pagina


@pytest.mark.parametrize("rota_informada, mensagem", [
    (None, "Selecione a rota da insígnia."),
    ("999", "Rota não encontrada."),
])
def test_painel_exige_uma_rota_existente(admin_client, db_session, rota, rota_informada, mensagem):
    campos = {} if rota_informada is None else {"route_id": rota_informada}

    resposta = criar_no_painel(admin_client, **campos)

    assert resposta.status_code == 400
    assert mensagem in html.unescape(resposta.text)


def test_painel_recusa_segunda_insignia_para_a_mesma_rota(admin_client, db_session, rota):
    insignia_da_rota(db_session, rota)

    resposta = criar_no_painel(admin_client, name="Outra", route_id=str(rota.id))

    assert resposta.status_code == 400
    assert "Esta rota já tem uma insígnia de conclusão: Concluiu o Centro." in html.unescape(resposta.text)


def test_editar_a_propria_insignia_mantendo_a_rota(admin_client, db_session, rota):
    badge = insignia_da_rota(db_session, rota)

    resposta = admin_client.post(f"/admin/badges/{badge.id}/edit", data={
        "name": "Concluiu!", "rule_type": "route_completion", "route_id": str(rota.id), "active": "true",
    }, follow_redirects=False)

    assert resposta.status_code == 303
    db_session.expire_all()
    assert db_session.get(Badge, badge.id).name == "Concluiu!"


def test_rota_com_insignia_nao_pode_ser_excluida(admin_client, db_session, rota):
    insignia_da_rota(db_session, rota)

    confirmacao = html.unescape(admin_client.get(f"/admin/routes/{rota.id}/delete").text)
    resposta = admin_client.post(f"/admin/routes/{rota.id}/delete", follow_redirects=False)

    assert "Tem a insígnia de conclusão: Concluiu o Centro." in confirmacao
    assert resposta.status_code == 409


# ---------- Eventos de rota (ADM-10) ----------

def test_eventos_de_iniciar_e_concluir(user_client, db_session, rota, pontos):
    fazer_a_rota(user_client, rota, pontos)

    assert eventos(db_session) == ["started", "completed"]


def test_evento_de_abandonar(user_client, db_session, rota):
    user_client.post(f"/routes/{rota.id}/start")
    user_client.delete("/users/me/active-route")

    assert eventos(db_session) == ["started", "abandoned"]


def test_evento_de_rota_encerrada_pelo_painel(user_client, admin_client, db_session, rota):
    user_client.post(f"/routes/{rota.id}/start")

    admin_client.post(f"/admin/routes/{rota.id}/status", data={"active": "false"})
    # Ver o aviso e depois "abandonar" não conta como abandono
    user_client.get("/users/me/active-route")

    assert eventos(db_session) == ["started", "cancelled"]


def test_iniciar_a_mesma_rota_de_novo_nao_gera_evento(user_client, db_session, rota):
    user_client.post(f"/routes/{rota.id}/start")
    user_client.post(f"/routes/{rota.id}/start")

    assert eventos(db_session) == ["started"]


# ---------- Migração 0015 ----------

def test_desfazer_a_0015_apaga_as_insignias_de_rota(tmp_path):
    url = f"sqlite:///{tmp_path / 'rotas.db'}"
    cfg = alembic_cfg(url)
    command.upgrade(cfg, "0015")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO routes (id, name, difficulty, age_rating) VALUES (1, 'Centro', 'easy', 'L')"
        ))
        conn.execute(text(
            "INSERT INTO badges (id, name, rule_type, required_count) VALUES (1, 'Cinco', 'visit_count', 5)"
        ))
        conn.execute(text(
            "INSERT INTO badges (id, name, rule_type, route_id) VALUES (2, 'Rota', 'route_completion', 1)"
        ))

    command.downgrade(cfg, "0014")

    with engine.connect() as conn:
        assert conn.execute(text("SELECT id FROM badges")).all() == [(1,)]
    engine.dispose()
