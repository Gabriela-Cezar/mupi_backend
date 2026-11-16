"""Rota ativa (ROT-05 a ROT-10): iniciar, ver, finalizar pontos na ordem,
encerrar, abandonar e rota alterada pelo administrador."""
import pytest

from app.model.mupi_object import MupiObject
from app.model.route import AgeRating, Route, RouteDifficulty, RoutePoint
from app.model.user_active_route import UserActiveRoute
from app.model.user_route_completion import UserRouteCompletion
from app.model.user_visit import UserVisit
from app.service.auth_service import gerar_password_hash

# Pontos a ~1 km um do outro
POSICOES = [(-16.680, -49.250), (-16.690, -49.250), (-16.700, -49.250)]


def perto(ponto):
    return {"latitude": ponto.latitude, "longitude": ponto.longitude}


def longe(ponto):
    return {"latitude": ponto.latitude + 0.01, "longitude": ponto.longitude}


@pytest.fixture
def pontos(db_session):
    """A e C existem sozinhos; B só existe em rotas (PT-09)."""
    lista = [
        MupiObject(name=nome, latitude=lat, longitude=lng, standalone=nome != "B")
        for nome, (lat, lng) in zip(["A", "B", "C"], POSICOES)
    ]
    db_session.add_all(lista)
    db_session.commit()
    return lista


def nova_rota(db_session, nome, pontos_, ativa=True):
    route = Route(
        name=nome, difficulty=RouteDifficulty.EASY, age_rating=AgeRating.FREE, active=ativa,
        cover_key="routes/x/cover.png",
        path=[[p.longitude, p.latitude] for p in pontos_],
        waypoints=list(range(len(pontos_))),
        distance_m=2000, walk_seconds=1500,
        points=[RoutePoint(object_id=p.id, position=i, mupi_object=p) for i, p in enumerate(pontos_)],
    )
    db_session.add(route)
    db_session.commit()
    return route


@pytest.fixture
def rota(db_session, pontos):
    return nova_rota(db_session, "Centro", pontos)


def iniciar(client, rota_):
    return client.post(f"/routes/{rota_.id}/start")


def abrir(client, ponto, posicao=None):
    return client.post(f"/mupi-objects/{ponto.id}/open", json=posicao or perto(ponto))


def finalizar(client, ponto, posicao=None):
    return client.post(
        f"/users/me/active-route/points/{ponto.id}/finish", json=posicao or perto(ponto)
    )


def abrir_e_finalizar(client, ponto):
    assert abrir(client, ponto).status_code == 200
    resposta = finalizar(client, ponto)
    assert resposta.status_code == 200, resposta.text
    return resposta


def ativa(client):
    return client.get("/users/me/active-route").json()


def estados(resposta_json):
    return [p["status"] for p in resposta_json["active_route"]["route"]["points"]]


# ---------- Iniciar (ROT-05) ----------

@pytest.mark.parametrize("metodo, url", [
    ("post", "/routes/1/start"),
    ("get", "/users/me/active-route"),
    ("delete", "/users/me/active-route"),
    ("post", "/users/me/active-route/complete"),
])
def test_exigem_login(client, metodo, url):
    assert getattr(client, metodo)(url).status_code == 401


def test_iniciar_comeca_pelo_primeiro_ponto(user_client, rota, pontos):
    resposta = iniciar(user_client, rota)

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["notice"] is None
    atual = dados["active_route"]
    assert atual["route"]["name"] == "Centro"
    assert atual["next_index"] == 0
    assert atual["next_point"] == {"id": pontos[0].id, "name": "A"}
    assert estados(dados) == ["current", "pending", "pending"]
    # Até o primeiro ponto o app usa o "Como chegar"
    assert atual["current_leg"] is None
    assert atual["all_finished"] is False


@pytest.mark.parametrize("ajuste", ["inativa", "sem_trajeto"])
def test_rota_indisponivel_nao_inicia(user_client, db_session, rota, ajuste):
    if ajuste == "inativa":
        rota.active = False
    else:
        rota.path = None
    db_session.commit()

    assert iniciar(user_client, rota).status_code == 404


def test_rota_inexistente_nao_inicia(user_client):
    assert user_client.post("/routes/999/start").status_code == 404


def test_outra_rota_em_andamento_responde_409_dizendo_qual(user_client, db_session, rota, pontos):
    outra = nova_rota(db_session, "Arte", pontos[:2])
    iniciar(user_client, rota)

    resposta = iniciar(user_client, outra)

    assert resposta.status_code == 409
    detalhe = resposta.json()["detail"]
    assert "Você está fazendo a rota Centro" in detalhe["message"]
    assert detalhe["active_route"] == {"id": rota.id, "name": "Centro"}
    assert ativa(user_client)["active_route"]["route"]["name"] == "Centro"


def test_iniciar_a_mesma_rota_de_novo_nao_recomeca(user_client, rota, pontos):
    iniciar(user_client, rota)
    abrir_e_finalizar(user_client, pontos[0])

    resposta = iniciar(user_client, rota)

    assert resposta.json()["active_route"]["next_index"] == 1


def test_depois_de_abandonar_pode_iniciar_outra(user_client, db_session, rota, pontos):
    outra = nova_rota(db_session, "Arte", pontos[:2])
    iniciar(user_client, rota)
    user_client.delete("/users/me/active-route")

    assert iniciar(user_client, outra).status_code == 200


# ---------- Ver (ROT-06) ----------

def test_sem_rota_ativa(user_client):
    assert ativa(user_client) == {"active_route": None, "notice": None}


def test_perfil_traz_a_rota_ativa(user_client, rota):
    assert user_client.get("/users/me").json()["active_route"] is None

    iniciar(user_client, rota)

    perfil = user_client.get("/users/me").json()
    assert perfil["active_route"]["route"]["id"] == rota.id
    assert perfil["active_route"]["next_index"] == 0


# ---------- Pontos que só existem em rotas (PT-09) ----------

def test_ponto_so_de_rota_abre_so_com_a_rota_ativa(user_client, rota, pontos):
    b = pontos[1]

    assert abrir(user_client, b).status_code == 404

    iniciar(user_client, rota)

    assert abrir(user_client, b).status_code == 200


def test_como_chegar_ao_ponto_so_de_rota_com_a_rota_ativa(user_client, rota, pontos, monkeypatch):
    from app.controller import mupi_object_controller

    monkeypatch.setattr(mupi_object_controller, "OPENROUTESERVICE_API_KEY", None)
    b = pontos[1]
    url = f"/mupi-objects/{b.id}/route?latitude=-16.68&longitude=-49.25"

    assert user_client.get(url).status_code == 404

    iniciar(user_client, rota)

    # Passou da conferência do ponto (falta só a chave, neste teste)
    assert user_client.get(url).status_code == 500


def test_ponto_so_de_rota_some_de_novo_ao_abandonar(user_client, rota, pontos):
    iniciar(user_client, rota)
    user_client.delete("/users/me/active-route")

    assert abrir(user_client, pontos[1]).status_code == 404


# ---------- Finalizar ponto (ROT-07) ----------

def test_sem_rota_ativa_nao_finaliza(user_client, pontos):
    resposta = finalizar(user_client, pontos[0])

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Você não está fazendo nenhuma rota."


def test_finalizar_avanca_para_o_proximo(user_client, rota, pontos):
    iniciar(user_client, rota)

    dados = abrir_e_finalizar(user_client, pontos[0]).json()

    atual = dados["active_route"]
    assert atual["next_index"] == 1
    assert atual["next_point"]["name"] == "B"
    assert estados(dados) == ["done", "current", "pending"]
    # Trecho do ponto A ao B
    assert atual["current_leg"] == 0


def test_fora_de_ordem_responde_409(user_client, rota, pontos):
    iniciar(user_client, rota)
    abrir(user_client, pontos[2])

    resposta = finalizar(user_client, pontos[2])

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "Finalize os pontos na ordem: o próximo é A."


def test_ponto_ja_finalizado_responde_409(user_client, rota, pontos):
    iniciar(user_client, rota)
    abrir_e_finalizar(user_client, pontos[0])

    resposta = finalizar(user_client, pontos[0])

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "Este ponto já foi finalizado."


def test_ponto_fora_da_rota_responde_409(user_client, db_session, rota):
    fora = MupiObject(name="Fora", latitude=-16.6, longitude=-49.2)
    db_session.add(fora)
    db_session.commit()
    iniciar(user_client, rota)

    resposta = finalizar(user_client, fora)

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "Este ponto não faz parte da rota."


def test_precisa_abrir_o_ponto_antes(user_client, rota, pontos):
    iniciar(user_client, rota)

    resposta = finalizar(user_client, pontos[0])

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "Abra o ponto antes de finalizar."


def test_visita_de_outro_dia_vale_mas_precisa_estar_perto(user_client, db_session, usuario, rota, pontos):
    """Quem já visitou o ponto antes só precisa estar perto agora."""
    db_session.add(UserVisit(user_id=usuario.id, object_id=pontos[0].id))
    db_session.commit()
    iniciar(user_client, rota)

    assert finalizar(user_client, pontos[0], longe(pontos[0])).status_code == 403
    assert finalizar(user_client, pontos[0]).status_code == 200


def test_dois_toques_juntos_nao_pulam_um_ponto(user_client, db_session, usuario, rota, pontos, monkeypatch):
    """Simula outro "finalizar" do mesmo ponto gravado entre a conferência e
    o avanço: este não pode avançar de novo."""
    from app.controller import active_route_controller

    iniciar(user_client, rota)
    abrir(user_client, pontos[0])
    original = active_route_controller.get_mupi_in_range

    def outro_toque_chega_antes(db, *args, **kwargs):
        db.query(UserActiveRoute).filter_by(user_id=usuario.id).update({"next_index": 1})
        db.commit()
        return original(db, *args, **kwargs)

    monkeypatch.setattr(active_route_controller, "get_mupi_in_range", outro_toque_chega_antes)

    resposta = finalizar(user_client, pontos[0])

    assert resposta.status_code == 409
    db_session.expire_all()
    assert db_session.get(UserActiveRoute, usuario.id).next_index == 1


# ---------- Encerrar (ROT-08) ----------

def test_nao_encerra_antes_de_finalizar_todos(user_client, rota, pontos):
    iniciar(user_client, rota)
    abrir_e_finalizar(user_client, pontos[0])

    resposta = user_client.post("/users/me/active-route/complete")

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "Finalize todos os pontos antes de encerrar a rota."


def test_encerrar_registra_a_conclusao_e_apaga_o_progresso(user_client, db_session, usuario, rota, pontos):
    iniciar(user_client, rota)
    for ponto in pontos:
        dados = abrir_e_finalizar(user_client, ponto).json()
    assert dados["active_route"]["all_finished"] is True
    assert estados(dados) == ["done", "done", "done"]

    resposta = user_client.post("/users/me/active-route/complete")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["route"]["completed"] is True
    assert corpo["completions"] == 1
    assert corpo["awarded"] == []
    assert ativa(user_client) == {"active_route": None, "notice": None}
    assert user_client.get("/routes").json()[0]["completed"] is True
    db_session.expire_all()
    assert db_session.query(UserRouteCompletion).filter_by(user_id=usuario.id).count() == 1


def test_refazer_uma_rota_concluida_conta_de_novo(user_client, rota, pontos):
    for _ in range(2):
        iniciar(user_client, rota)
        for ponto in pontos:
            abrir_e_finalizar(user_client, ponto)
        resposta = user_client.post("/users/me/active-route/complete")

    assert resposta.json()["completions"] == 2


# ---------- Abandonar (ROT-09) ----------

def test_abandonar_apaga_o_progresso_e_mantem_as_visitas(user_client, db_session, usuario, rota, pontos):
    iniciar(user_client, rota)
    abrir_e_finalizar(user_client, pontos[0])

    resposta = user_client.delete("/users/me/active-route")

    assert resposta.status_code == 200
    assert ativa(user_client)["active_route"] is None
    db_session.expire_all()
    assert db_session.get(UserVisit, (usuario.id, pontos[0].id)) is not None
    # Para fazer de novo, recomeça do primeiro ponto
    assert iniciar(user_client, rota).json()["active_route"]["next_index"] == 0


def test_abandonar_sem_rota_responde_404(user_client):
    assert user_client.delete("/users/me/active-route").status_code == 404


# ---------- Rota alterada pelo administrador (ROT-10) ----------

def editar_no_painel(admin_client, rota_, **campos):
    dados = {
        "name": rota_.name, "difficulty": "easy", "age_rating": "L",
        "point_ids": [str(i) for i in rota_.point_ids], "active": "true", **campos,
    }
    return admin_client.post(f"/admin/routes/{rota_.id}/edit", data=dados, follow_redirects=False)


@pytest.fixture
def com_ors(ors):
    """O painel recalcula o trajeto ao mudar os pontos."""
    return ors


def test_mudar_a_ordem_encerra_o_progresso_e_avisa_uma_vez(user_client, admin_client, rota, pontos, com_ors):
    iniciar(user_client, rota)
    a, b, c = pontos

    editar_no_painel(admin_client, rota, point_ids=[str(c.id), str(b.id), str(a.id)])

    assert ativa(user_client) == {
        "active_route": None, "notice": "Esta rota foi atualizada; inicie novamente.",
    }
    # O aviso aparece uma vez só
    assert ativa(user_client) == {"active_route": None, "notice": None}


def test_mudar_so_o_nome_nao_afeta_o_progresso(user_client, admin_client, rota, pontos, com_ors):
    iniciar(user_client, rota)
    abrir_e_finalizar(user_client, pontos[0])

    editar_no_painel(admin_client, rota, name="Centro Histórico")

    assert ativa(user_client)["active_route"]["next_index"] == 1


def test_desativar_a_rota_encerra_o_progresso(user_client, admin_client, rota):
    iniciar(user_client, rota)

    admin_client.post(f"/admin/routes/{rota.id}/status", data={"active": "false"})

    assert ativa(user_client)["notice"] == (
        "Esta rota não está mais disponível; o seu progresso foi encerrado."
    )


def test_desativar_um_ponto_da_rota_encerra_o_progresso(user_client, admin_client, rota, pontos):
    iniciar(user_client, rota)

    admin_client.post(f"/admin/mupi-objects/{pontos[2].id}/status", data={"active": "false"})

    assert ativa(user_client)["notice"] is not None


def test_finalizar_depois_de_encerrada_pelo_painel_avisa(user_client, admin_client, rota, pontos):
    iniciar(user_client, rota)
    abrir(user_client, pontos[0])
    admin_client.post(f"/admin/routes/{rota.id}/status", data={"active": "false"})

    resposta = finalizar(user_client, pontos[0])

    assert resposta.status_code == 409
    assert "não está mais disponível" in resposta.json()["detail"]
    assert ativa(user_client) == {"active_route": None, "notice": None}


def test_depois_do_aviso_pode_iniciar_outra(user_client, admin_client, db_session, rota, pontos):
    outra = nova_rota(db_session, "Arte", pontos[:2])
    iniciar(user_client, rota)
    admin_client.post(f"/admin/routes/{rota.id}/status", data={"active": "false"})

    # Sem ver o aviso antes: a encerrada não bloqueia
    assert iniciar(user_client, outra).status_code == 200


def test_painel_avisa_quantos_estao_fazendo_a_rota(user_client, admin_client, rota):
    iniciar(user_client, rota)

    pagina = admin_client.get(f"/admin/routes/{rota.id}/edit").text

    assert "1 usuário(s) estão fazendo esta rota agora." in pagina


# ---------- Conta ----------

def test_excluir_a_conta_apaga_o_progresso(user_client, db_session, usuario, rota):
    usuario.password_hash = gerar_password_hash("Senha-123")
    db_session.commit()
    iniciar(user_client, rota)

    user_client.request("DELETE", "/users/me", json={"password": "Senha-123"})

    db_session.expire_all()
    assert db_session.query(UserActiveRoute).count() == 0
