import polyline
import pytest

from app.controller import mupi_object_controller
from app.core.security import create_access_token
from app.model.badge import Badge, BadgeRule
from app.model.midia import MediaType, MupiObjectMedia
from app.model.mupi_object import MupiObject
from app.model.theme import Theme
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit
from app.service.proximity_service import PROXIMITY_RADIUS_M

PNG = b"\x89PNG\r\n\x1a\n" + b"conteudo-da-imagem"

LAT, LNG = -23.5505, -46.6333
PERTO = {"latitude": LAT, "longitude": LNG}
LONGE = {"latitude": LAT - 0.01, "longitude": LNG}  # ~1,1 km ao sul

CAMPOS_DO_RESUMO = {
    "id", "name", "latitude", "longitude", "theme", "photo_url", "has_video", "visited",
}
CAMPOS_DO_CONTEUDO = {"description", "media", "badges"}


@pytest.fixture
def tema(db_session):
    tema = Theme(name="Arte Deco")
    db_session.add(tema)
    db_session.commit()
    return tema


@pytest.fixture
def insignia_do_ponto(db_session):
    insignia = Badge(
        name="Visitou o Edifício",
        description="Segredo até chegar",
        rule_type=BadgeRule.MANUAL,
        image=PNG,
        image_mime_type="image/png",
    )
    db_session.add(insignia)
    db_session.commit()
    return insignia


@pytest.fixture
def ponto(db_session, tema, insignia_do_ponto):
    ponto = MupiObject(
        name="Edifício Exemplo",
        description="Texto que só aparece perto do ponto.",
        latitude=LAT,
        longitude=LNG,
        active=True,
        theme_id=tema.id,
        badges=[insignia_do_ponto],
        media=[
            MupiObjectMedia(type=MediaType.IMAGE, data=PNG, mime_type="image/png", title="foto.png"),
            MupiObjectMedia(type=MediaType.VIDEO, url="https://youtu.be/abc123"),
        ],
    )
    db_session.add(ponto)
    db_session.commit()
    return ponto


@pytest.fixture
def ponto_inativo(db_session):
    ponto = MupiObject(
        name="Edifício Desativado",
        description="Não deve aparecer.",
        latitude=LAT,
        longitude=LNG,
        active=False,
        media=[MupiObjectMedia(type=MediaType.IMAGE, data=PNG, mime_type="image/png")],
    )
    db_session.add(ponto)
    db_session.commit()
    return ponto


@pytest.fixture
def ponto_sem_midia(db_session):
    ponto = MupiObject(name="Praça Sem Mídia", latitude=LAT + 0.001, longitude=LNG, active=True)
    db_session.add(ponto)
    db_session.commit()
    return ponto


def foto(ponto):
    return next(m for m in ponto.media if m.type == MediaType.IMAGE)


def abrir(client, ponto, posicao=PERTO):
    return client.post(f"/mupi-objects/{ponto.id}/open", json=posicao)


# ---------- Login obrigatório ----------

ROTAS_GET = [
    "/mupi-objects",
    f"/mupi-objects/nearby?latitude={LAT}&longitude={LNG}&radius=1000",
    f"/mupi-objects/search?name=Edi&latitude={LAT}&longitude={LNG}",
    f"/mupi-objects/1/route?latitude={LAT}&longitude={LNG}",
    "/mupi-objects/media/1",
    "/mupi-objects/1/image",
    "/mupi-objects/badges/1/image",
]


@pytest.mark.parametrize("rota", ROTAS_GET)
def test_rotas_do_app_exigem_login(client, ponto, rota):
    resposta = client.get(rota)

    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "Sessão inválida ou expirada. Entre novamente."


def test_abrir_ponto_exige_login(client, db_session, ponto):
    resposta = abrir(client, ponto)

    assert resposta.status_code == 401
    assert db_session.query(UserVisit).count() == 0


@pytest.mark.parametrize("cabecalho", ["Bearer token-invalido", "Basic abc", "Bearer "])
def test_token_invalido_e_recusado(client, ponto, cabecalho):
    resposta = client.get("/mupi-objects", headers={"Authorization": cabecalho})

    assert resposta.status_code == 401


def test_token_de_usuario_desativado_e_recusado(user_client, db_session, usuario, ponto):
    usuario.is_active = False
    db_session.commit()

    assert user_client.get("/mupi-objects").status_code == 401


def test_sessao_do_painel_nao_serve_para_o_app(admin_client, ponto):
    """O admin logado no painel não é um usuário do aplicativo."""
    del admin_client.headers["X-CSRF-Token"]

    assert admin_client.get("/mupi-objects").status_code == 401


# ---------- Resumo: mapa, próximos e busca ----------

def test_lista_traz_so_o_resumo(user_client, ponto):
    [item] = user_client.get("/mupi-objects").json()

    assert set(item) == CAMPOS_DO_RESUMO
    assert item == {
        "id": ponto.id,
        "name": "Edifício Exemplo",
        "latitude": LAT,
        "longitude": LNG,
        "theme": {"id": ponto.theme_id, "name": "Arte Deco"},
        "photo_url": f"/mupi-objects/media/{foto(ponto).id}",
        "has_video": True,
        "visited": False,
    }


def test_resumo_nao_vaza_conteudo(user_client, ponto):
    texto = user_client.get("/mupi-objects").text

    assert "Texto que só aparece perto" not in texto
    assert "youtu.be" not in texto
    assert "Visitou o Edifício" not in texto


def test_ponto_sem_midia_e_sem_tema(user_client, ponto_sem_midia):
    [item] = user_client.get("/mupi-objects").json()

    assert item["photo_url"] is None
    assert item["has_video"] is False
    assert item["theme"] is None


def test_lista_nao_mostra_pontos_inativos(user_client, ponto, ponto_inativo):
    nomes = [p["name"] for p in user_client.get("/mupi-objects").json()]

    assert nomes == ["Edifício Exemplo"]


def test_lista_marca_pontos_visitados_pelo_usuario(user_client, db_session, usuario, ponto, ponto_sem_midia):
    db_session.add(UserVisit(user_id=usuario.id, object_id=ponto.id))
    db_session.commit()

    visitados = {p["name"]: p["visited"] for p in user_client.get("/mupi-objects").json()}

    assert visitados == {"Edifício Exemplo": True, "Praça Sem Mídia": False}


def test_visita_de_outro_usuario_nao_conta(user_client, db_session, ponto):
    from app.model.user import User

    outro = User(email="outro@exemplo.com", password_hash="x")
    db_session.add(outro)
    db_session.commit()
    db_session.add(UserVisit(user_id=outro.id, object_id=ponto.id))
    db_session.commit()

    [item] = user_client.get("/mupi-objects").json()

    assert item["visited"] is False


def test_proximos_traz_resumo_com_distancia(user_client, ponto, ponto_inativo):
    resposta = user_client.get(
        "/mupi-objects/nearby", params={**PERTO, "radius": 500}
    )

    [item] = resposta.json()
    assert set(item) == CAMPOS_DO_RESUMO | {"distance"}
    assert item["distance"] == 0


def test_busca_traz_resumo_com_distancia(user_client, ponto, ponto_inativo):
    resposta = user_client.get(
        "/mupi-objects/search", params={"name": "edifício", **LONGE}
    )

    [item] = resposta.json()
    assert set(item) == CAMPOS_DO_RESUMO | {"distance"}
    assert item["distance"] > 1000


# ---------- Abrir o ponto ----------

def test_abrir_longe_retorna_403_sem_conteudo_e_sem_visita(user_client, db_session, ponto):
    resposta = abrir(user_client, ponto, LONGE)

    assert resposta.status_code == 403
    assert "Aproxime-se do MUPI" in resposta.json()["detail"]
    assert f"o limite é {PROXIMITY_RADIUS_M} m" in resposta.json()["detail"]
    assert "Texto que só aparece perto" not in resposta.text
    assert db_session.query(UserVisit).count() == 0


def test_abrir_perto_entrega_o_conteudo_completo(user_client, ponto, insignia_do_ponto):
    resposta = abrir(user_client, ponto)

    assert resposta.status_code == 200
    dados = resposta.json()
    assert set(dados) == CAMPOS_DO_RESUMO | CAMPOS_DO_CONTEUDO | {
        "new_visit", "visits_total", "awarded",
    }
    assert dados["description"] == "Texto que só aparece perto do ponto."
    assert [m["type"] for m in dados["media"]] == ["image", "video"]
    assert dados["media"][1]["url"] == "https://youtu.be/abc123"
    assert [b["name"] for b in dados["badges"]] == ["Visitou o Edifício"]
    assert dados["visited"] is True


def test_abrir_perto_registra_a_visita(user_client, db_session, usuario, ponto):
    dados = abrir(user_client, ponto).json()

    assert dados["new_visit"] is True
    assert dados["visits_total"] == 1
    assert db_session.get(UserVisit, (usuario.id, ponto.id)) is not None


def test_abrir_de_novo_nao_duplica_a_visita(user_client, db_session, ponto):
    abrir(user_client, ponto)

    segunda = abrir(user_client, ponto).json()

    assert segunda["new_visit"] is False
    assert segunda["visits_total"] == 1
    assert db_session.query(UserVisit).count() == 1


def test_depois_de_aberto_aparece_como_visitado_no_mapa(user_client, ponto):
    abrir(user_client, ponto)

    [item] = user_client.get("/mupi-objects").json()

    assert item["visited"] is True


def test_abrir_concede_insignia_de_contagem(user_client, db_session, usuario, ponto):
    contagem = Badge(name="Primeira visita", rule_type=BadgeRule.VISIT_COUNT, required_count=1)
    db_session.add(contagem)
    db_session.commit()

    dados = abrir(user_client, ponto).json()

    assert [b["name"] for b in dados["awarded"]] == ["Primeira visita"]
    assert dados["awarded"][0]["collected_at_object"] == {
        "id": ponto.id, "name": "Edifício Exemplo",
    }
    assert db_session.get(UserBadge, (usuario.id, contagem.id)) is not None


def test_abrir_um_pouco_dentro_do_limite_funciona(user_client, ponto):
    # ~0,9 do limite ao norte (1 grau de latitude ≈ 111 km)
    deslocamento = PROXIMITY_RADIUS_M * 0.9 / 111_195
    resposta = abrir(user_client, ponto, {"latitude": LAT + deslocamento, "longitude": LNG})

    assert resposta.status_code == 200


def test_abrir_um_pouco_fora_do_limite_e_recusado(user_client, ponto):
    deslocamento = PROXIMITY_RADIUS_M * 1.1 / 111_195
    resposta = abrir(user_client, ponto, {"latitude": LAT + deslocamento, "longitude": LNG})

    assert resposta.status_code == 403


def test_abrir_ponto_inativo_retorna_404(user_client, db_session, ponto_inativo):
    resposta = abrir(user_client, ponto_inativo)

    assert resposta.status_code == 404
    assert db_session.query(UserVisit).count() == 0


def test_abrir_ponto_inexistente_retorna_404(user_client):
    resposta = user_client.post("/mupi-objects/999/open", json=PERTO)

    assert resposta.status_code == 404


@pytest.mark.parametrize("posicao", [
    {},
    {"latitude": 91, "longitude": 0},
    {"latitude": 0, "longitude": 181},
    {"latitude": "abc", "longitude": 0},
])
def test_abrir_com_posicao_invalida_retorna_422(user_client, ponto, posicao):
    assert abrir(user_client, ponto, posicao).status_code == 422


# ---------- Arquivos ----------

def test_foto_e_entregue_ao_usuario_logado(user_client, ponto):
    resposta = user_client.get(f"/mupi-objects/media/{foto(ponto).id}")

    assert resposta.status_code == 200
    assert resposta.content == PNG
    assert resposta.headers["content-type"] == "image/png"
    assert resposta.headers["cache-control"].startswith("private")


def test_foto_de_ponto_inativo_nao_e_entregue(user_client, ponto_inativo):
    resposta = user_client.get(f"/mupi-objects/media/{foto(ponto_inativo).id}")

    assert resposta.status_code == 404


def test_rota_antiga_de_imagem_nao_entrega_ponto_inativo(user_client, ponto_inativo):
    """FAL-16: antes a imagem de ponto desativado continuava acessível."""
    assert user_client.get(f"/mupi-objects/{ponto_inativo.id}/image").status_code == 404


def test_rota_antiga_de_imagem_funciona_para_ponto_ativo(user_client, ponto):
    resposta = user_client.get(f"/mupi-objects/{ponto.id}/image")

    assert resposta.status_code == 200
    assert resposta.headers["cache-control"].startswith("private")


def test_imagem_da_insignia_e_entregue_ao_usuario_logado(user_client, insignia_do_ponto):
    resposta = user_client.get(f"/mupi-objects/badges/{insignia_do_ponto.id}/image")

    assert resposta.status_code == 200
    assert resposta.content == PNG
    assert resposta.headers["cache-control"].startswith("private")


# ---------- Rota a pé até o ponto ----------

class RespostaFalsa:
    status_code = 200
    text = ""

    def json(self):
        return {"routes": [{
            "geometry": polyline.encode([(LAT - 0.001, LNG), (LAT, LNG)]),
            "summary": {"distance": 111.2, "duration": 80.0},
        }]}


def test_rota_a_pe_funciona_com_login(user_client, ponto, monkeypatch):
    monkeypatch.setattr(mupi_object_controller, "OPENROUTESERVICE_API_KEY", "chave-falsa")
    monkeypatch.setattr(mupi_object_controller.requests, "post", lambda *a, **k: RespostaFalsa())

    resposta = user_client.get(f"/mupi-objects/{ponto.id}/route", params=LONGE)

    assert resposta.status_code == 200
    assert resposta.json()["mupi_id"] == ponto.id
    assert resposta.json()["coordinates"][-1] == [LNG, LAT]


def test_rota_a_pe_para_ponto_inativo_retorna_404(user_client, ponto_inativo, monkeypatch):
    monkeypatch.setattr(mupi_object_controller, "OPENROUTESERVICE_API_KEY", "chave-falsa")

    resposta = user_client.get(f"/mupi-objects/{ponto_inativo.id}/route", params=LONGE)

    assert resposta.status_code == 404


# ---------- Rotas antigas do app continuam funcionando ----------

def test_check_in_antigo_continua_funcionando(user_client, db_session, usuario, ponto):
    perto = user_client.post("/users/me/visits", json={"object_id": ponto.id, **PERTO})
    longe = user_client.post("/users/me/visits", json={"object_id": ponto.id, **LONGE})

    assert perto.status_code == 200
    assert perto.json()["new_visit"] is True
    assert longe.status_code == 403


def test_coleta_manual_antiga_continua_funcionando(user_client, ponto, insignia_do_ponto):
    resposta = user_client.post(
        "/users/me/badges",
        json={"object_id": ponto.id, "badge_id": insignia_do_ponto.id, **PERTO},
    )

    assert resposta.status_code == 200
    assert resposta.json()["badge"]["name"] == "Visitou o Edifício"


def test_perfil_continua_funcionando(user_client, ponto):
    abrir(user_client, ponto)

    perfil = user_client.get("/users/me").json()

    assert perfil["visits_total"] == 1


def test_token_criado_para_outro_id_e_recusado(client, ponto):
    token = create_access_token(999, "hash-qualquer")

    resposta = client.get("/mupi-objects", headers={"Authorization": f"Bearer {token}"})

    assert resposta.status_code == 401
