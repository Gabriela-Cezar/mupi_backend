"""Temas no painel: lista, cadastro, edição e exclusão (ADM-05, ADM-09, ADM-12)."""
import html

import pytest

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.mupi_object_theme import MupiObjectTheme
from app.model.theme import Theme


@pytest.fixture
def client(admin_client):
    """Todas as rotas deste arquivo são do painel: usa um admin logado."""
    return admin_client


URL = "/admin/themes"


def criar_tema(client, **campos):
    return client.post(URL, data=campos, follow_redirects=False)


def temas_salvos(db_session):
    db_session.expire_all()
    return db_session.query(Theme).order_by(Theme.id).all()


def texto(resposta) -> str:
    """O HTML da resposta com as entidades convertidas (ex.: &#39; → ')."""
    return html.unescape(resposta.text)


@pytest.fixture
def arte_deco(db_session):
    tema = Theme(name="Arte Deco", description="Edifícios Art Déco")
    db_session.add(tema)
    db_session.commit()
    return tema


def ponto_com_tema(db_session, tema, nome="Edifício"):
    ponto = MupiObject(name=nome, latitude=0, longitude=0, themes=[tema])
    db_session.add(ponto)
    db_session.commit()
    return ponto


def insignia_do_tema(db_session, tema):
    insignia = Badge(
        name="3 pontos Arte Deco",
        rule_type=BadgeRule.THEME_VISIT_COUNT,
        required_count=3,
        theme_id=tema.id,
    )
    db_session.add(insignia)
    db_session.commit()
    return insignia


# ---------- Página (lista + cadastro) ----------

def test_pagina_abre_com_o_formulario_de_cadastro(client):
    resposta = client.get(URL)

    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert 'action="/admin/themes"' in resposta.text
    assert 'name="name"' in resposta.text
    assert 'name="description"' in resposta.text


def test_endereco_antigo_leva_a_pagina_de_temas(client):
    resposta = client.get(f"{URL}/new", follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == URL


def test_pagina_sem_temas_avisa(client):
    assert "Nenhum tema cadastrado ainda." in client.get(URL).text


def test_lista_em_ordem_alfabetica_com_descricao(client, db_session, arte_deco):
    db_session.add(Theme(name="Modernismo"))
    db_session.commit()

    pagina = client.get(URL).text

    assert "Nenhum tema cadastrado ainda." not in pagina
    assert "Edifícios Art Déco" in pagina
    assert pagina.index("Arte Deco") < pagina.index("Modernismo")


def test_lista_mostra_quantos_pontos_e_insignias_usam_o_tema(client, db_session, arte_deco):
    ponto_com_tema(db_session, arte_deco, "A")
    ponto_com_tema(db_session, arte_deco, "B")
    insignia_do_tema(db_session, arte_deco)

    pagina = client.get(URL).text

    linha = pagina[pagina.index("<strong>Arte Deco</strong>"):]
    linha = linha[:linha.index("</tr>")]
    assert "<td>2</td>" in linha
    assert "<td>1</td>" in linha
    assert f'href="/admin/themes/{arte_deco.id}/edit"' in linha
    assert f'href="/admin/themes/{arte_deco.id}/delete"' in linha


def test_pagina_escapa_html_do_nome(client, db_session):
    db_session.add(Theme(name="<script>alert(1)</script>"))
    db_session.commit()

    pagina = client.get(URL).text

    assert "<script>alert(1)</script>" not in pagina
    assert "&lt;script&gt;" in pagina


# ---------- Cadastro ----------

def test_cria_tema_e_volta_para_a_lista_com_mensagem(client, db_session):
    resposta = criar_tema(client, name="Arte Deco", description="Edifícios Art Déco")

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/admin/themes?msg=theme-created"
    [tema] = temas_salvos(db_session)
    assert tema.name == "Arte Deco"
    assert tema.description == "Edifícios Art Déco"

    assert "Tema cadastrado." in client.get(resposta.headers["location"]).text


def test_remove_espacos_do_nome_e_da_descricao(client, db_session):
    criar_tema(client, name="  Arte Deco  ", description="  Descrição  ")

    [tema] = temas_salvos(db_session)
    assert tema.name == "Arte Deco"
    assert tema.description == "Descrição"


@pytest.mark.parametrize("descricao", [None, "", "   "])
def test_descricao_vazia_fica_nula(client, db_session, descricao):
    campos = {"name": "Arte Deco"}
    if descricao is not None:
        campos["description"] = descricao

    criar_tema(client, **campos)

    assert temas_salvos(db_session)[0].description is None


def test_tema_cadastrado_aparece_nos_outros_formularios(client):
    criar_tema(client, name="Arte Deco")

    assert "Arte Deco" in client.get("/admin/mupi-objects/new").text
    assert "Arte Deco" in client.get("/admin/badges/new").text


def test_mensagem_desconhecida_na_url_nao_aparece(client):
    """O texto da mensagem nunca vem da URL."""
    pagina = client.get(URL, params={"msg": "<b>golpe</b>"}).text

    assert "golpe" not in pagina
    assert "alert-success" not in pagina


# ---------- Erros: o formulário volta com a mensagem e o que foi digitado ----------

@pytest.mark.parametrize("campos, mensagem", [
    ({"name": "   "}, "Informe o nome do tema."),
    ({"description": "Sem nome"}, "Informe o nome do tema."),
    ({"name": "a" * 101}, "Nome: máximo de 100 caracteres."),
    ({"name": "Ok", "description": "x" * 2001}, "Descrição: máximo de 2000 caracteres."),
])
def test_dados_invalidos_retornam_400_com_mensagem(client, db_session, campos, mensagem):
    resposta = criar_tema(client, **campos)

    assert resposta.status_code == 400
    assert mensagem in texto(resposta)
    assert temas_salvos(db_session) == []


def test_erro_mantem_o_que_foi_digitado(client, arte_deco):
    resposta = criar_tema(client, name="arte deco", description="Minha descrição")

    assert 'value="arte deco"' in resposta.text
    assert "Minha descrição</textarea>" in resposta.text


@pytest.mark.parametrize("repetido", ["Arte Deco", "arte deco", "  ARTE DECO "])
def test_nome_repetido_retorna_400(client, db_session, arte_deco, repetido):
    resposta = criar_tema(client, name=repetido)

    assert resposta.status_code == 400
    assert "Já existe um tema com esse nome." in texto(resposta)
    assert len(temas_salvos(db_session)) == 1


# ---------- Edição ----------

def test_tela_de_edicao_vem_preenchida(client, arte_deco):
    resposta = client.get(f"{URL}/{arte_deco.id}/edit")

    assert resposta.status_code == 200
    assert 'value="Arte Deco"' in resposta.text
    assert "Edifícios Art Déco</textarea>" in resposta.text
    assert f'action="/admin/themes/{arte_deco.id}/edit"' in resposta.text


def test_editar_tema(client, db_session, arte_deco):
    resposta = client.post(
        f"{URL}/{arte_deco.id}/edit",
        data={"name": "Art Déco", "description": ""},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/admin/themes?msg=theme-updated"
    [tema] = temas_salvos(db_session)
    assert (tema.name, tema.description) == ("Art Déco", None)


def test_editar_mantendo_o_mesmo_nome_funciona(client, db_session, arte_deco):
    resposta = client.post(
        f"{URL}/{arte_deco.id}/edit",
        data={"name": "ARTE DECO", "description": "Nova"},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert temas_salvos(db_session)[0].name == "ARTE DECO"


def test_editar_para_nome_de_outro_tema_retorna_400(client, db_session, arte_deco):
    db_session.add(Theme(name="Modernismo"))
    db_session.commit()

    resposta = client.post(
        f"{URL}/{arte_deco.id}/edit", data={"name": "modernismo"}, follow_redirects=False
    )

    assert resposta.status_code == 400
    assert "Já existe um tema com esse nome." in texto(resposta)
    assert 'value="modernismo"' in resposta.text
    assert temas_salvos(db_session)[0].name == "Arte Deco"


def test_editar_tema_inexistente_retorna_404(client):
    assert client.get(f"{URL}/999/edit").status_code == 404
    assert client.post(f"{URL}/999/edit", data={"name": "X"}).status_code == 404


# ---------- Exclusão (ADM-09) ----------

def test_confirmacao_avisa_quantos_pontos_perdem_o_tema(client, db_session, arte_deco):
    ponto_com_tema(db_session, arte_deco)

    resposta = client.get(f"{URL}/{arte_deco.id}/delete")

    assert resposta.status_code == 200
    assert "1 ponto(s) deixam de ter este tema" in resposta.text
    assert f'action="/admin/themes/{arte_deco.id}/delete"' in resposta.text
    # A confirmação não exclui nada
    assert len(temas_salvos(db_session)) == 1


def test_excluir_tema_remove_so_as_ligacoes_e_os_pontos_continuam(client, db_session, arte_deco):
    ponto = ponto_com_tema(db_session, arte_deco)

    resposta = client.post(f"{URL}/{arte_deco.id}/delete", follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/admin/themes?msg=theme-deleted"
    assert temas_salvos(db_session) == []
    assert db_session.query(MupiObjectTheme).count() == 0
    assert db_session.get(MupiObject, ponto.id).themes == []


def test_tema_usado_por_insignia_nao_pode_ser_excluido(client, db_session, arte_deco):
    insignia_do_tema(db_session, arte_deco)

    confirmacao = client.get(f"{URL}/{arte_deco.id}/delete")
    resposta = client.post(f"{URL}/{arte_deco.id}/delete", follow_redirects=False)

    assert "Não é possível excluir" in confirmacao.text
    assert "Excluir definitivamente" not in confirmacao.text
    assert resposta.status_code == 409
    assert "3 pontos Arte Deco" in resposta.text
    assert len(temas_salvos(db_session)) == 1


def test_excluir_tema_inexistente_retorna_404(client):
    assert client.post(f"{URL}/999/delete").status_code == 404
