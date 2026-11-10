import pytest

from app.model.theme import Theme


@pytest.fixture
def client(admin_client):
    """Todas as rotas deste arquivo são do painel: usa um admin logado."""
    return admin_client


URL = "/admin/themes"


def criar_tema(client, **campos):
    return client.post(URL, data=campos)


def temas_salvos(db_session):
    db_session.expire_all()
    return db_session.query(Theme).order_by(Theme.id).all()


# ---------- Página do formulário ----------

def test_pagina_de_cadastro_abre_com_os_campos(client):
    resposta = client.get(f"{URL}/new")

    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert 'action="/admin/themes"' in resposta.text
    assert 'name="name"' in resposta.text
    assert 'name="description"' in resposta.text


def test_pagina_sem_temas_avisa(client):
    html = client.get(f"{URL}/new").text

    assert "Nenhum tema cadastrado ainda." in html


def test_pagina_lista_temas_em_ordem_alfabetica(client, db_session):
    db_session.add_all([
        Theme(name="Modernismo"),
        Theme(name="Arte Deco", description="Edifícios Art Déco"),
    ])
    db_session.commit()

    html = client.get(f"{URL}/new").text

    assert "Nenhum tema cadastrado ainda." not in html
    assert "Edifícios Art Déco" in html
    assert html.index("Arte Deco") < html.index("Modernismo")


def test_pagina_escapa_html_do_nome(client, db_session):
    db_session.add(Theme(name="<script>alert(1)</script>"))
    db_session.commit()

    html = client.get(f"{URL}/new").text

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---------- Cadastro ----------

def test_cria_tema_com_nome_e_descricao(client, db_session):
    resposta = criar_tema(client, name="Arte Deco", description="Edifícios Art Déco")

    assert resposta.status_code == 200
    assert resposta.json()["message"] == "Tema cadastrado com sucesso!"
    [tema] = temas_salvos(db_session)
    assert tema.id == resposta.json()["id"]
    assert tema.name == "Arte Deco"
    assert tema.description == "Edifícios Art Déco"


def test_remove_espacos_do_nome_e_da_descricao(client, db_session):
    resposta = criar_tema(client, name="  Arte Deco  ", description="  Descrição  ")

    assert resposta.status_code == 200
    [tema] = temas_salvos(db_session)
    assert tema.name == "Arte Deco"
    assert tema.description == "Descrição"


@pytest.mark.parametrize("descricao", [None, "", "   "])
def test_descricao_vazia_fica_nula(client, db_session, descricao):
    campos = {"name": "Arte Deco"}
    if descricao is not None:
        campos["description"] = descricao

    resposta = criar_tema(client, **campos)

    assert resposta.status_code == 200
    assert temas_salvos(db_session)[0].description is None


def test_tema_cadastrado_aparece_nos_outros_formularios(client):
    criar_tema(client, name="Arte Deco")

    assert "Arte Deco" in client.get("/admin/mupi-objects").text
    assert "Arte Deco" in client.get("/admin/badges").text


# ---------- Erros ----------

def test_nome_so_com_espacos_retorna_400(client, db_session):
    resposta = criar_tema(client, name="   ")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Informe o nome do tema."
    assert temas_salvos(db_session) == []


def test_sem_nome_retorna_422(client, db_session):
    resposta = criar_tema(client, description="Sem nome")

    assert resposta.status_code == 422
    assert temas_salvos(db_session) == []


def test_nome_com_mais_de_100_caracteres_retorna_422(client, db_session):
    resposta = criar_tema(client, name="a" * 101)

    assert resposta.status_code == 422
    assert temas_salvos(db_session) == []


@pytest.mark.parametrize("repetido", ["Arte Deco", "arte deco", "  ARTE DECO "])
def test_nome_repetido_retorna_400(client, db_session, repetido):
    criar_tema(client, name="Arte Deco")

    resposta = criar_tema(client, name=repetido)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Já existe um tema com esse nome."
    assert len(temas_salvos(db_session)) == 1


# ---------- Lista em JSON (rota já existente) ----------

def test_lista_json_continua_funcionando(client):
    criar_tema(client, name="Modernismo")
    criar_tema(client, name="Arte Deco", description="Art Déco")

    resposta = client.get(URL)

    assert resposta.status_code == 200
    assert [t["name"] for t in resposta.json()] == ["Arte Deco", "Modernismo"]
    assert resposta.json()[0]["description"] == "Art Déco"
