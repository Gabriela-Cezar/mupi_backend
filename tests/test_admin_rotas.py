"""Rotas no painel: lista, cadastro com pontos em ordem, trajeto, ativação e
exclusão (ADM-07, ADM-08, ADM-09; ROT-01 a ROT-03)."""
import html

import pytest

from app.model.mupi_object import MupiObject
from app.model.route import AgeRating, Route, RouteDifficulty, RoutePoint
from app.model.theme import Theme
from tests.conftest import chaves_no_bucket
from tests.ors_falso import RespostaFalsa

URL = "/admin/routes"
PNG = b"\x89PNG\r\n\x1a\n" + b"capa"


@pytest.fixture
def client(admin_client):
    return admin_client


@pytest.fixture
def pontos(db_session):
    """Três pontos ativos: A, B e C."""
    lista = [
        MupiObject(name=nome, latitude=-16.68 - i / 100, longitude=-49.25 - i / 100)
        for i, nome in enumerate(["Ponto A", "Ponto B", "Ponto C"])
    ]
    db_session.add_all(lista)
    db_session.commit()
    return lista


def ids(*pontos_):
    return [str(p.id) for p in pontos_]


def criar(client, pontos_, arquivos=None, **campos):
    dados = {
        "name": "Centro Histórico",
        "difficulty": "easy",
        "age_rating": "L",
        "point_ids": ids(*pontos_),
        **campos,
    }
    return client.post(URL, data=dados, files=arquivos or {}, follow_redirects=False)


def com_capa():
    return {"cover": ("capa.png", PNG, "image/png")}


def salva(db_session, nome="Centro Histórico") -> Route:
    db_session.expire_all()
    return db_session.query(Route).filter_by(name=nome).one()


def texto(resposta) -> str:
    return html.unescape(resposta.text)


@pytest.fixture
def rota(client, db_session, ors, pontos):
    """Rota completa e ativa: A → B → C, com capa e trajeto."""
    criar(client, pontos, com_capa(), active="true")
    route = salva(db_session)
    assert route.active
    ors.pedidos.clear()
    return route


def editar(client, route, arquivos=None, **campos):
    dados = {
        "name": route.name,
        "description": route.description or "",
        "difficulty": route.difficulty.value,
        "age_rating": route.age_rating.value,
        "point_ids": [str(i) for i in route.point_ids],
        "estimated_minutes": str(route.estimated_minutes or ""),
        "active": "true" if route.active else "",
        **campos,
    }
    return client.post(f"{URL}/{route.id}/edit", data=dados, files=arquivos or {}, follow_redirects=False)


# ---------- Lista ----------

def test_lista_vazia(client):
    pagina = client.get(URL)

    assert "Nenhuma rota cadastrada ainda." in pagina.text
    assert 'href="/admin/routes/new"' in pagina.text


def test_lista_mostra_pontos_distancia_tempo_e_dificuldade(client, rota):
    pagina = texto(client.get(URL))

    linha = pagina[pagina.index("<strong>Centro Histórico</strong>"):]
    linha = linha[:linha.index("</tr>")]
    assert "Ativa" in linha
    assert "<td>3</td>" in linha
    assert "1,2 km" in linha
    assert "15 min" in linha
    assert "Fácil" in linha


def test_menu_do_painel_tem_rotas(client):
    assert 'href="/admin/routes"' in client.get("/admin/mupi-objects").text


# ---------- Formulário ----------

def test_formulario_tem_os_campos(client, db_session, pontos):
    pontos[2].active = False
    pontos[1].standalone = False
    db_session.add(Theme(name="Arte Deco"))
    db_session.commit()

    pagina = texto(client.get(f"{URL}/new"))

    for campo in ("name", "description", "difficulty", "age_rating", "theme_ids",
                  "estimated_minutes", "cover", "active"):
        assert f'name="{campo}"' in pagina, campo
    for valor in ("easy", "medium", "hard", "L", "10", "12", "14", "16", "18"):
        assert f'value="{valor}"' in pagina
    assert "Ponto B (só em rotas)" in pagina
    # Ponto desativado aparece, mas não pode ser escolhido
    assert f'value="{pontos[2].id}" disabled' in pagina


# ---------- Cadastro ----------

def test_cria_rota_completa_e_ativa(client, db_session, ors, pontos):
    resposta = criar(client, pontos, com_capa(), active="true", estimated_minutes="40")

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/admin/routes?msg=route-created"
    route = salva(db_session)
    assert route.active is True
    assert route.point_ids == [p.id for p in pontos]
    assert route.has_path
    assert route.minutes == 40
    assert route.cover_key.startswith(f"routes/{route.id}/cover-")
    # O trajeto foi pedido na ordem dos pontos
    assert ors.coordenadas_pedidas[0] == [pontos[0].longitude, pontos[0].latitude]


def test_a_ordem_do_formulario_e_a_ordem_da_rota(client, db_session, ors, pontos):
    a, b, c = pontos

    criar(client, [c, a, b])

    assert salva(db_session).point_ids == [c.id, a.id, b.id]


def test_cria_com_temas(client, db_session, ors, pontos):
    tema = Theme(name="Arte Deco")
    db_session.add(tema)
    db_session.commit()

    criar(client, pontos, theme_ids=[str(tema.id)])

    assert [t.name for t in salva(db_session).themes] == ["Arte Deco"]


def test_sem_capa_a_rota_e_salva_desativada(client, db_session, ors, pontos):
    resposta = criar(client, pontos, active="true")

    route = salva(db_session)
    assert route.active is False
    assert resposta.headers["location"] == f"/admin/routes/{route.id}/edit?msg=route-saved-inactive"

    edicao = texto(client.get(resposta.headers["location"]))
    assert "Para ativar a rota, falta:" in edicao
    assert "Envie a imagem de capa." in edicao


def test_falha_no_trajeto_salva_sem_trajeto_e_mostra_o_erro(client, db_session, ors, pontos):
    ors.resposta = RespostaFalsa(404, {"error": {"message": "Could not find routable point"}})

    resposta = criar(client, pontos, com_capa(), active="true")

    route = salva(db_session)
    assert route.active is False
    assert route.has_path is False
    assert resposta.headers["location"] == f"/admin/routes/{route.id}/edit?msg=route-saved-path-error"

    edicao = texto(client.get(resposta.headers["location"]))
    assert "Could not find routable point" in edicao
    assert f'action="/admin/routes/{route.id}/path"' in edicao
    assert "Recalcular trajeto" in edicao


@pytest.mark.parametrize("campos, mensagem", [
    ({"name": " "}, "Informe o nome da rota."),
    ({"name": "a" * 151}, "Nome: máximo de 150 caracteres."),
    ({"difficulty": "radical"}, "Escolha a dificuldade."),
    ({"age_rating": "21"}, "Escolha a classificação indicativa."),
    ({"estimated_minutes": "0"}, "Tempo estimado"),
    ({"estimated_minutes": "muito"}, "Tempo estimado"),
    ({"estimated_minutes": "2000"}, "Tempo estimado"),
])
def test_erros_voltam_ao_formulario(client, db_session, ors, pontos, campos, mensagem):
    resposta = criar(client, pontos, **campos)

    assert resposta.status_code == 400
    assert mensagem in texto(resposta)
    assert db_session.query(Route).count() == 0
    assert ors.pedidos == []


def test_precisa_de_pelo_menos_dois_pontos(client, db_session, ors, pontos):
    resposta = criar(client, pontos[:1])

    assert resposta.status_code == 400
    assert "A rota precisa de pelo menos 2 pontos." in texto(resposta)


def test_ponto_repetido_e_recusado(client, db_session, ors, pontos):
    a, b, _ = pontos

    resposta = criar(client, [a, b, a])

    assert "O mesmo ponto não pode aparecer duas vezes na rota." in texto(resposta)


def test_ponto_inexistente_e_recusado(client, db_session, ors, pontos):
    resposta = client.post(URL, data={
        "name": "X", "difficulty": "easy", "age_rating": "L",
        "point_ids": [str(pontos[0].id), "999"],
    })

    assert "Ponto não encontrado." in texto(resposta)


def test_ponto_desativado_nao_entra(client, db_session, ors, pontos):
    pontos[2].active = False
    db_session.commit()

    resposta = criar(client, pontos)

    assert resposta.status_code == 400
    assert "Ponto desativado não pode entrar na rota: Ponto C." in texto(resposta)


def test_nome_repetido(client, db_session, rota, pontos):
    resposta = criar(client, pontos, name="centro histórico")

    assert resposta.status_code == 400
    assert "Já existe uma rota com esse nome." in texto(resposta)


def test_erro_mantem_os_pontos_na_ordem_escolhida(client, ors, pontos):
    a, b, c = pontos

    pagina = texto(criar(client, [c, a], name=""))

    assert pagina.index("Ponto C") < pagina.index("Ponto A")
    assert f'name="point_ids" value="{c.id}"' in pagina
    assert "Se você tinha escolhido uma imagem, escolha de novo." in pagina


# ---------- Edição ----------

def test_edicao_vem_preenchida_com_o_mapa(client, rota, pontos):
    pagina = texto(client.get(f"{URL}/{rota.id}/edit"))

    assert 'value="Centro Histórico"' in pagina
    assert 'id="route-map"' in pagina
    assert "leaflet" in pagina
    assert "1,2 km" in pagina
    # O campo exato do ponto: só `value="1"` também casaria com o token CSRF
    primeiro = pagina.index(f'name="point_ids" value="{pontos[0].id}"')
    ultimo = pagina.index(f'name="point_ids" value="{pontos[2].id}"')
    assert primeiro < ultimo
    assert "Para ativar a rota" not in pagina


def test_mudar_so_o_nome_nao_recalcula_o_trajeto(client, db_session, ors, rota):
    resposta = editar(client, rota, name="Centro")

    assert resposta.headers["location"] == "/admin/routes?msg=route-updated"
    assert ors.pedidos == []
    assert salva(db_session, "Centro").has_path


def test_mudar_a_ordem_recalcula_e_nao_esbarra_nas_chaves_unicas(client, db_session, ors, rota, pontos):
    a, b, c = pontos

    editar(client, rota, point_ids=ids(c, b, a))

    route = salva(db_session)
    assert route.point_ids == [c.id, b.id, a.id]
    assert [rp.position for rp in route.points] == [0, 1, 2]
    assert ors.coordenadas_pedidas[0] == [c.longitude, c.latitude]
    assert db_session.query(RoutePoint).count() == 3


def test_tirar_um_ponto_recalcula(client, db_session, ors, rota, pontos):
    editar(client, rota, point_ids=ids(pontos[0], pontos[2]))

    assert salva(db_session).point_ids == [pontos[0].id, pontos[2].id]
    assert len(ors.pedidos) == 1


def test_ponto_que_ja_estava_e_foi_desativado_pode_ficar(client, db_session, ors, rota, pontos):
    pontos[1].active = False
    db_session.commit()

    resposta = editar(client, rota, name="Centro", active="true")

    route = salva(db_session, "Centro")
    # Salva, mas não ativa até o ponto ser corrigido
    assert route.active is False
    assert resposta.headers["location"].endswith("msg=route-saved-inactive")
    assert "Ponto desativado na rota: Ponto B." in texto(client.get(f"{URL}/{route.id}/edit"))


def test_substituir_a_capa_apaga_a_anterior(client, db_session, s3_simulado, rota):
    antiga = rota.cover_key

    editar(client, rota, {"cover": ("nova.png", PNG, "image/png")})

    route = salva(db_session)
    assert route.cover_key != antiga
    assert chaves_no_bucket(s3_simulado) == [route.cover_key]


def test_remover_a_capa_desativa(client, db_session, s3_simulado, rota):
    editar(client, rota, remove_cover="true")

    route = salva(db_session)
    assert route.cover_key is None
    assert route.active is False
    assert chaves_no_bucket(s3_simulado) == []


def test_editar_inexistente(client):
    assert client.get(f"{URL}/999/edit").status_code == 404


# ---------- Recalcular trajeto ----------

def test_recalcular_trajeto(client, db_session, ors, rota):
    ors.resposta = RespostaFalsa(429, {})
    client.post(f"{URL}/{rota.id}/path")
    assert salva(db_session).has_path is False

    ors.resposta = None
    resposta = client.post(f"{URL}/{rota.id}/path", follow_redirects=False)

    assert resposta.headers["location"] == f"/admin/routes/{rota.id}/edit?msg=route-path-updated"
    assert salva(db_session).has_path


def test_recalcular_com_erro_avisa(client, ors, rota):
    ors.resposta = RespostaFalsa(429, {})

    resposta = client.post(f"{URL}/{rota.id}/path", follow_redirects=False)

    assert resposta.headers["location"].endswith("msg=route-path-error")
    assert "Cota do serviço de trajetos esgotada" in texto(client.get(resposta.headers["location"]))


# ---------- Ativar e desativar ----------

def test_desativar_e_ativar(client, db_session, rota):
    desativar = client.post(f"{URL}/{rota.id}/status", data={"active": "false"}, follow_redirects=False)
    assert desativar.headers["location"] == "/admin/routes?msg=route-deactivated"
    assert salva(db_session).active is False

    ativar = client.post(f"{URL}/{rota.id}/status", data={"active": "true"}, follow_redirects=False)
    assert ativar.headers["location"] == "/admin/routes?msg=route-activated"
    assert salva(db_session).active is True


def test_ativar_rota_incompleta_explica_o_que_falta(client, db_session, ors, pontos):
    criar(client, pontos)
    route = salva(db_session)

    resposta = client.post(f"{URL}/{route.id}/status", data={"active": "true"})

    assert resposta.status_code == 400
    assert "não pode ser ativada: Envie a imagem de capa." in texto(resposta)
    assert salva(db_session).active is False


# ---------- Pontos desativados e excluídos (ROT-02, ADM-09) ----------

def test_desativar_um_ponto_desativa_as_rotas_dele(client, db_session, rota, pontos):
    resposta = client.post(
        f"/admin/mupi-objects/{pontos[1].id}/status", data={"active": "false"}, follow_redirects=False,
    )

    assert resposta.headers["location"].endswith("msg=point-deactivated-routes")
    assert salva(db_session).active is False
    assert "As rotas que passam por ele também foram desativadas" in texto(
        client.get(resposta.headers["location"])
    )
    lista = texto(client.get(URL))
    assert "Ponto desativado" in lista


def test_desativar_ponto_fora_de_rotas_usa_a_mensagem_comum(client, db_session, rota):
    sozinho = MupiObject(name="Sozinho", latitude=0, longitude=0)
    db_session.add(sozinho)
    db_session.commit()

    resposta = client.post(
        f"/admin/mupi-objects/{sozinho.id}/status", data={"active": "false"}, follow_redirects=False,
    )

    assert resposta.headers["location"].endswith("msg=point-deactivated")
    assert salva(db_session).active is True


def test_desativar_o_ponto_pela_edicao_tambem_desativa_as_rotas(client, db_session, rota, pontos):
    ponto = pontos[0]

    resposta = client.post(
        f"/admin/mupi-objects/{ponto.id}/edit",
        data={"name": ponto.name, "latitude": str(ponto.latitude), "longitude": str(ponto.longitude)},
        follow_redirects=False,
    )

    assert resposta.headers["location"].endswith("msg=point-updated-routes")
    assert salva(db_session).active is False


def test_ponto_de_uma_rota_nao_pode_ser_excluido(client, db_session, rota, pontos):
    confirmacao = texto(client.get(f"/admin/mupi-objects/{pontos[0].id}/delete"))
    resposta = client.post(f"/admin/mupi-objects/{pontos[0].id}/delete", follow_redirects=False)

    assert "Faz parte da rota: Centro Histórico." in confirmacao
    assert resposta.status_code == 409
    db_session.expire_all()
    assert db_session.get(MupiObject, pontos[0].id) is not None


# ---------- Temas ----------

def test_excluir_tema_tira_das_rotas_e_avisa(client, db_session, ors, pontos):
    tema = Theme(name="Arte Deco")
    db_session.add(tema)
    db_session.commit()
    criar(client, pontos, theme_ids=[str(tema.id)])

    confirmacao = texto(client.get(f"/admin/themes/{tema.id}/delete"))
    client.post(f"/admin/themes/{tema.id}/delete")

    assert "1 rota(s) deixam de ter este tema" in confirmacao
    assert salva(db_session).themes == []


# ---------- Excluir ----------

def test_excluir_rota(client, db_session, s3_simulado, rota, pontos):
    confirmacao = texto(client.get(f"{URL}/{rota.id}/delete"))
    resposta = client.post(f"{URL}/{rota.id}/delete", follow_redirects=False)

    assert "Os pontos continuam cadastrados." in confirmacao
    assert "A imagem de capa é apagada do armazenamento." in confirmacao
    assert resposta.headers["location"] == "/admin/routes?msg=route-deleted"
    db_session.expire_all()
    assert db_session.query(Route).count() == 0
    assert db_session.query(RoutePoint).count() == 0
    assert db_session.query(MupiObject).count() == 3
    assert chaves_no_bucket(s3_simulado) == []


def test_excluir_inexistente(client):
    assert client.post(f"{URL}/999/delete").status_code == 404


# ---------- Modelo ----------

def test_banco_recusa_o_mesmo_ponto_duas_vezes(db_session, pontos):
    from sqlalchemy.exc import IntegrityError

    route = Route(name="X", difficulty=RouteDifficulty.EASY, age_rating=AgeRating.FREE)
    route.points = [
        RoutePoint(object_id=pontos[0].id, position=0),
        RoutePoint(object_id=pontos[0].id, position=1),
    ]
    db_session.add(route)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_rota_nova_comeca_desativada(db_session):
    route = Route(name="X", difficulty=RouteDifficulty.EASY, age_rating=AgeRating.FREE)
    db_session.add(route)
    db_session.commit()

    assert route.active is False
