"""Conteúdo próprio de um ponto dentro de uma rota: painel e app.

Quem abre o ponto fazendo a rota vê o conteúdo da rota (nome, foto, blocos,
áudio, vídeos, informações do local) no lugar do conteúdo do ponto. Fora da
rota, ou fazendo outra, vale o conteúdo normal do ponto.
"""
import html

import pytest

from app.model.mupi_object import MupiObject
from app.model.mupi_object_section import MupiObjectSection
from app.model.route import Route
from app.model.route_point_content import RoutePointContent
from tests.conftest import chaves_no_bucket
from tests.test_admin_rotas import com_capa, criar, editar, salva

PNG = b"\x89PNG\r\n\x1a\n" + b"foto-da-rota"


@pytest.fixture
def pontos(db_session):
    lista = [
        MupiObject(
            name=nome, latitude=-16.68 - i / 100, longitude=-49.25 - i / 100,
            photo_key=f"points/{i}/photo-original.png",
            sections=[MupiObjectSection(position=0, title="História", body=f"Texto do {nome}")],
        )
        for i, nome in enumerate(["Ponto A", "Ponto B", "Ponto C"])
    ]
    db_session.add_all(lista)
    db_session.commit()
    return lista


@pytest.fixture
def rota(admin_client, db_session, ors, pontos):
    criar(admin_client, pontos, com_capa(), active="true")
    route = salva(db_session)
    assert route.active
    return route


def url(route, ponto):
    return f"/admin/routes/{route.id}/points/{ponto.id}/content"


def salvar(admin_client, route, ponto, arquivos=None, **campos):
    dados = {
        "name": "A na rota",
        "section_title": ["Na rota"],
        "section_body": ["Texto só da rota"],
        "video_url": ["https://youtu.be/dQw4w9WgXcQ"],
        "video_title": ["Vídeo da rota"],
        "address": "",
        **campos,
    }
    return admin_client.post(url(route, ponto), data=dados, files=arquivos or {}, follow_redirects=False)


def conteudo(db_session, route, ponto):
    db_session.expire_all()
    return db_session.query(RoutePointContent).filter_by(route_id=route.id, object_id=ponto.id).first()


def abrir(client, ponto):
    return client.post(
        f"/mupi-objects/{ponto.id}/open",
        json={"latitude": ponto.latitude, "longitude": ponto.longitude},
    )


# ---------- Painel ----------

def test_edicao_da_rota_tem_link_para_o_conteudo_de_cada_ponto(admin_client, rota, pontos):
    pagina = admin_client.get(f"/admin/routes/{rota.id}/edit").text

    for ponto in pontos:
        assert f'href="{url(rota, ponto)}"' in pagina
    assert "conteúdo próprio" not in pagina


def test_formulario_comeca_com_o_conteudo_do_ponto(admin_client, rota, pontos):
    pagina = html.unescape(admin_client.get(url(rota, pontos[0])).text)

    assert "Ponto A na rota Centro Histórico" in pagina
    assert "Texto do Ponto A" in pagina
    assert "ainda usa o próprio conteúdo" in pagina
    assert "Usar o conteúdo do ponto" not in pagina


def test_ponto_fora_da_rota_nao_tem_conteudo_nela(admin_client, db_session, rota):
    fora = MupiObject(name="Fora", latitude=-16.7, longitude=-49.3)
    db_session.add(fora)
    db_session.commit()

    assert admin_client.get(url(rota, fora)).status_code == 404
    assert salvar(admin_client, rota, fora).status_code == 404


def test_salvar_o_conteudo_do_ponto_na_rota(admin_client, db_session, s3_simulado, rota, pontos):
    resposta = salvar(admin_client, rota, pontos[0], {"photo": ("f.png", PNG, "image/png")})

    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/admin/routes/{rota.id}/edit?msg=route-point-content-saved"

    salvo = conteudo(db_session, rota, pontos[0])
    assert salvo.name == "A na rota"
    assert [(s.title, s.body) for s in salvo.sections] == [("Na rota", "Texto só da rota")]
    assert [(v.youtube_id, v.title) for v in salvo.videos] == [("dQw4w9WgXcQ", "Vídeo da rota")]
    assert salvo.photo_key.startswith(f"routes/{rota.id}/points/{pontos[0].id}/photo")
    assert salvo.photo_key in chaves_no_bucket(s3_simulado)
    # O ponto não muda
    db_session.expire_all()
    assert db_session.get(MupiObject, pontos[0].id).name == "Ponto A"

    pagina = html.unescape(admin_client.get(f"/admin/routes/{rota.id}/edit?msg=route-point-content-saved").text)
    assert "Conteúdo do ponto nesta rota salvo." in pagina
    assert "conteúdo próprio" in pagina


def test_salvar_de_novo_atualiza_e_troca_a_foto(admin_client, db_session, s3_simulado, rota, pontos):
    salvar(admin_client, rota, pontos[0], {"photo": ("f.png", PNG, "image/png")})
    antiga = conteudo(db_session, rota, pontos[0]).photo_key

    salvar(admin_client, rota, pontos[0], {"photo": ("g.png", PNG + b"2", "image/png")},
           name="", section_title=[], section_body=[], video_url=[], video_title=[])

    salvo = conteudo(db_session, rota, pontos[0])
    assert salvo.name is None
    assert salvo.sections == [] and salvo.videos == []
    assert antiga not in chaves_no_bucket(s3_simulado)
    assert salvo.photo_key in chaves_no_bucket(s3_simulado)


def test_erro_no_formulario_nao_salva(admin_client, db_session, rota, pontos):
    resposta = salvar(admin_client, rota, pontos[0], section_title=[""], section_body=["Sem título"])

    assert resposta.status_code == 400
    assert "Bloco 1: informe o título." in html.unescape(resposta.text)
    assert conteudo(db_session, rota, pontos[0]) is None


def test_voltar_ao_conteudo_do_ponto(admin_client, db_session, s3_simulado, rota, pontos):
    salvar(admin_client, rota, pontos[0], {"photo": ("f.png", PNG, "image/png")})
    chave = conteudo(db_session, rota, pontos[0]).photo_key

    resposta = admin_client.post(f"{url(rota, pontos[0])}/delete", follow_redirects=False)

    assert resposta.status_code == 303
    assert "route-point-content-deleted" in resposta.headers["location"]
    assert conteudo(db_session, rota, pontos[0]) is None
    assert chave not in chaves_no_bucket(s3_simulado)


def test_ponto_que_sai_da_rota_perde_o_conteudo_nela(admin_client, db_session, s3_simulado, rota, pontos):
    salvar(admin_client, rota, pontos[0], {"photo": ("f.png", PNG, "image/png")})
    salvar(admin_client, rota, pontos[1])
    chave = conteudo(db_session, rota, pontos[0]).photo_key

    # Tira o A; o B continua
    editar(admin_client, salva(db_session), point_ids=[str(pontos[1].id), str(pontos[2].id)])

    assert conteudo(db_session, rota, pontos[0]) is None
    assert conteudo(db_session, rota, pontos[1]) is not None
    assert chave not in chaves_no_bucket(s3_simulado)


def test_reordenar_mantem_o_conteudo(admin_client, db_session, rota, pontos):
    salvar(admin_client, rota, pontos[0])

    editar(admin_client, salva(db_session), point_ids=[str(p.id) for p in reversed(pontos)])

    assert conteudo(db_session, rota, pontos[0]).name == "A na rota"


def test_excluir_a_rota_apaga_o_conteudo_e_os_arquivos(admin_client, db_session, s3_simulado, rota, pontos):
    salvar(admin_client, rota, pontos[0], {"photo": ("f.png", PNG, "image/png")})
    chave = conteudo(db_session, rota, pontos[0]).photo_key
    admin_client.post(f"/admin/routes/{rota.id}/status", data={"active": "false"})

    resposta = admin_client.post(f"/admin/routes/{rota.id}/delete", follow_redirects=False)

    assert resposta.status_code == 303
    db_session.expire_all()
    assert db_session.query(RoutePointContent).count() == 0
    assert chave not in chaves_no_bucket(s3_simulado)


# ---------- App ----------

def test_fora_de_rota_o_ponto_mostra_o_proprio_conteudo(user_client, admin_client, rota, pontos):
    salvar(admin_client, rota, pontos[0])

    dados = abrir(user_client, pontos[0]).json()

    assert dados["name"] == "Ponto A"
    assert [s["body"] for s in dados["sections"]] == ["Texto do Ponto A"]
    assert dados["route_content"] is None


def test_fazendo_a_rota_o_ponto_mostra_o_conteudo_dela(user_client, admin_client, s3_simulado, rota, pontos):
    salvar(admin_client, rota, pontos[0], {"photo": ("f.png", PNG, "image/png")}, address="Rua da Rota")
    user_client.post(f"/routes/{rota.id}/start")

    dados = abrir(user_client, pontos[0]).json()

    assert dados["name"] == "A na rota"
    assert [(s["title"], s["body"]) for s in dados["sections"]] == [("Na rota", "Texto só da rota")]
    assert [v["youtube_id"] for v in dados["videos"]] == ["dQw4w9WgXcQ"]
    assert dados["has_video"] is True
    assert f"routes/{rota.id}/points/" in dados["photo_url"]
    assert dados["address"] == "Rua da Rota"
    # A rota não tem áudio para o ponto: não toca o do ponto
    assert dados["audio"] is None
    assert dados["route_content"] == {"route_id": rota.id, "route_name": "Centro Histórico"}
    # A posição é a do ponto
    assert (dados["latitude"], dados["longitude"]) == (pontos[0].latitude, pontos[0].longitude)


def test_nome_e_foto_em_branco_valem_os_do_ponto(user_client, admin_client, rota, pontos):
    salvar(admin_client, rota, pontos[0], name="")
    user_client.post(f"/routes/{rota.id}/start")

    dados = abrir(user_client, pontos[0]).json()

    assert dados["name"] == "Ponto A"
    assert "photo-original" in dados["photo_url"]
    assert dados["sections"][0]["body"] == "Texto só da rota"


def test_ponto_sem_conteudo_na_rota_mostra_o_proprio(user_client, admin_client, rota, pontos):
    salvar(admin_client, rota, pontos[0])
    user_client.post(f"/routes/{rota.id}/start")

    dados = abrir(user_client, pontos[1]).json()

    assert dados["name"] == "Ponto B"
    assert dados["route_content"] is None


def test_fazendo_outra_rota_vale_o_conteudo_do_ponto(user_client, admin_client, db_session, rota, pontos):
    salvar(admin_client, rota, pontos[0])
    criar(admin_client, pontos, com_capa(), active="true", name="Outra rota")
    outra = salva(db_session, "Outra rota")
    user_client.post(f"/routes/{outra.id}/start")

    assert abrir(user_client, pontos[0]).json()["name"] == "Ponto A"


def test_detalhes_e_rota_ativa_usam_o_nome_da_rota(user_client, admin_client, rota, pontos):
    salvar(admin_client, rota, pontos[0])

    detalhes = user_client.get(f"/routes/{rota.id}").json()
    ativa = user_client.post(f"/routes/{rota.id}/start").json()

    assert [p["name"] for p in detalhes["points"]] == ["A na rota", "Ponto B", "Ponto C"]
    assert ativa["active_route"]["next_point"]["name"] == "A na rota"


def test_conteudo_some_do_app_quando_volta_ao_do_ponto(user_client, admin_client, rota, pontos):
    salvar(admin_client, rota, pontos[0])
    user_client.post(f"/routes/{rota.id}/start")
    admin_client.post(f"{url(rota, pontos[0])}/delete")

    assert abrir(user_client, pontos[0]).json()["name"] == "Ponto A"


def test_conteudo_vai_junto_com_a_rota_no_banco(db_session, rota, pontos):
    """CASCADE no banco: apagar a rota apaga o conteúdo dos pontos nela."""
    db_session.add(RoutePointContent(route_id=rota.id, object_id=pontos[0].id, name="X"))
    db_session.commit()

    db_session.delete(db_session.get(Route, rota.id))
    db_session.commit()

    assert db_session.query(RoutePointContent).count() == 0
