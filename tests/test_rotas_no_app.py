"""Rotas no app: listar e ver (ROT-04); conclusões (user_route_completions)."""
import pytest

from app.model.mupi_object import MupiObject
from app.model.route import AgeRating, Route, RouteDifficulty, RoutePoint
from app.model.theme import Theme
from app.model.user import User
from app.model.user_route_completion import UserRouteCompletion
from app.model.user_visit import UserVisit
from app.service.auth_service import gerar_password_hash


def nova_rota(db_session, nome, pontos, ativa=True, **extras):
    route = Route(
        name=nome,
        difficulty=RouteDifficulty.MEDIUM,
        age_rating=AgeRating.AGE_12,
        active=ativa,
        cover_key=f"routes/{nome}/cover.png",
        path=[[-49.25, -16.68], [-49.255, -16.685], [-49.26, -16.69]],
        waypoints=[0, 2],
        distance_m=1234.4,
        walk_seconds=900,
        points=[RoutePoint(object_id=p.id, position=i, mupi_object=p) for i, p in enumerate(pontos)],
        **extras,
    )
    db_session.add(route)
    db_session.commit()
    return route


@pytest.fixture
def pontos(db_session):
    a = MupiObject(name="Teatro", latitude=-16.68, longitude=-49.25, photo_key="points/1/photo.png")
    # Ponto que só existe em rotas (PT-09): aparece na rota
    b = MupiObject(name="Beco", latitude=-16.69, longitude=-49.26, standalone=False)
    db_session.add_all([a, b])
    db_session.commit()
    return a, b


@pytest.fixture
def rota(db_session, pontos):
    tema = Theme(name="Arte Deco")
    db_session.add(tema)
    db_session.commit()
    return nova_rota(db_session, "Centro", pontos, themes=[tema], description="Passeio pelo centro")


def concluir(db_session, usuario, rota):
    db_session.add(UserRouteCompletion(user_id=usuario.id, route_id=rota.id))
    db_session.commit()


# ---------- GET /routes ----------

@pytest.mark.parametrize("url", ["/routes", "/routes/1"])
def test_exigem_login(client, url):
    assert client.get(url).status_code == 401


def test_lista_vazia(user_client):
    assert user_client.get("/routes").json() == []


def test_lista_traz_o_resumo(user_client, rota):
    [item] = user_client.get("/routes").json()

    assert set(item) == {
        "id", "name", "cover_url", "distance_m", "minutes", "difficulty",
        "age_rating", "themes", "points_count", "completed",
    }
    assert item["name"] == "Centro"
    assert "routes/Centro/cover.png" in item["cover_url"]
    assert item["distance_m"] == 1234
    assert item["minutes"] == 15
    assert item["difficulty"] == "medium"
    assert item["age_rating"] == "12"
    assert item["themes"] == [{"id": rota.themes[0].id, "name": "Arte Deco"}]
    assert item["points_count"] == 2
    assert item["completed"] is False


def test_lista_so_tem_rotas_ativas_em_ordem_alfabetica(user_client, db_session, pontos, rota):
    nova_rota(db_session, "Arte", pontos)
    nova_rota(db_session, "Desativada", pontos, ativa=False)

    assert [r["name"] for r in user_client.get("/routes").json()] == ["Arte", "Centro"]


def test_tempo_estimado_editado_vale_na_lista(user_client, db_session, rota):
    rota.estimated_minutes = 50
    db_session.commit()

    assert user_client.get("/routes").json()[0]["minutes"] == 50


def test_marca_as_rotas_que_o_usuario_concluiu(user_client, db_session, usuario, pontos, rota):
    nova_rota(db_session, "Arte", pontos)
    concluir(db_session, usuario, rota)
    concluir(db_session, usuario, rota)  # refez a rota

    lista = {r["name"]: r["completed"] for r in user_client.get("/routes").json()}

    assert lista == {"Centro": True, "Arte": False}


def test_conclusao_de_outro_usuario_nao_conta(user_client, db_session, rota):
    outro = User(email="outro@exemplo.com", password_hash="x", email_verified=True)
    db_session.add(outro)
    db_session.commit()
    concluir(db_session, outro, rota)

    assert user_client.get("/routes").json()[0]["completed"] is False


# ---------- GET /routes/{id} ----------

def test_detalhe_traz_pontos_em_ordem_e_trajeto(user_client, db_session, usuario, rota, pontos):
    teatro, beco = pontos
    db_session.add(UserVisit(user_id=usuario.id, object_id=teatro.id))
    db_session.commit()

    detalhe = user_client.get(f"/routes/{rota.id}").json()

    assert detalhe["description"] == "Passeio pelo centro"
    assert [p["name"] for p in detalhe["points"]] == ["Teatro", "Beco"]
    primeiro = detalhe["points"][0]
    assert set(primeiro) == {"id", "name", "latitude", "longitude", "photo_url", "visited"}
    assert "points/1/photo.png" in primeiro["photo_url"]
    assert primeiro["visited"] is True
    assert detalhe["points"][1]["visited"] is False
    # O ponto que só existe em rotas aparece aqui
    assert detalhe["points"][1]["id"] == beco.id
    assert detalhe["path"][0] == [-49.25, -16.68]
    assert detalhe["waypoints"] == [0, 2]


def test_detalhe_nao_traz_o_conteudo_dos_pontos(user_client, rota):
    detalhe = user_client.get(f"/routes/{rota.id}").json()

    for ponto in detalhe["points"]:
        assert not {"sections", "videos", "audio", "badges"} & set(ponto)


def test_rota_desativada_ou_inexistente_retorna_404(user_client, db_session, pontos):
    desativada = nova_rota(db_session, "Desativada", pontos, ativa=False)

    assert user_client.get(f"/routes/{desativada.id}").status_code == 404
    assert user_client.get("/routes/999").status_code == 404


# ---------- Conclusões ----------

def test_rota_concluida_nao_pode_ser_excluida_no_painel(admin_client, db_session, usuario, rota):
    concluir(db_session, usuario, rota)

    confirmacao = admin_client.get(f"/admin/routes/{rota.id}/delete").text
    resposta = admin_client.post(f"/admin/routes/{rota.id}/delete", follow_redirects=False)

    assert "1 usuário já concluiu esta rota." in confirmacao
    assert "Excluir definitivamente" not in confirmacao
    assert resposta.status_code == 409
    db_session.expire_all()
    assert db_session.get(Route, rota.id) is not None


def test_excluir_a_conta_apaga_as_conclusoes(user_client, db_session, usuario, rota):
    usuario.password_hash = gerar_password_hash("Senha-123")
    db_session.commit()
    concluir(db_session, usuario, rota)

    resposta = user_client.request("DELETE", "/users/me", json={"password": "Senha-123"})

    assert resposta.status_code == 200
    db_session.expire_all()
    assert db_session.query(UserRouteCompletion).count() == 0
    assert db_session.get(Route, rota.id) is not None
