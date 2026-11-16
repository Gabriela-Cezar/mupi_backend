"""Insígnias no painel: lista, cadastro, edição, ativar/desativar e exclusão
(ADM-06, ADM-08, ADM-09, ADM-12)."""
import html
import re

import pytest

from app.controller import admin_files
from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.theme import Theme
from app.model.user import User
from app.model.user_badge import UserBadge
from app.service import storage_service
from tests.conftest import BUCKET_DE_TESTE, chaves_no_bucket

URL = "/admin/badges"
PNG = b"\x89PNG\r\n\x1a\n" + b"imagem-nova"
IMAGEM_ANTIGA = b"\x89PNG\r\n\x1a\n" + b"imagem-antiga"


@pytest.fixture
def client(admin_client):
    """Todas as rotas deste arquivo são do painel: usa um admin logado."""
    return admin_client


@pytest.fixture
def tema(db_session):
    tema = Theme(name="Arte Deco")
    db_session.add(tema)
    db_session.commit()
    return tema


@pytest.fixture
def teatro(db_session):
    ponto = MupiObject(name="Teatro Goiânia", latitude=0, longitude=0)
    db_session.add(ponto)
    db_session.commit()
    return ponto


@pytest.fixture
def insignia(db_session, teatro, s3_simulado):
    """Insígnia de visita com imagem já no S3."""
    chave = "badges/1/image-antiga.png"
    s3_simulado.put_object(Bucket=BUCKET_DE_TESTE, Key=chave, Body=IMAGEM_ANTIGA)

    badge = Badge(
        name="Visitou o Teatro",
        description="Você esteve lá",
        rule_type=BadgeRule.POINT_VISIT,
        object_id=teatro.id,
        image_key=chave,
    )
    db_session.add(badge)
    db_session.commit()
    return badge


def conquistar(db_session, badge, quantos=1):
    for i in range(quantos):
        usuario = User(email=f"u{i}-{badge.id}@exemplo.com", password_hash="x", email_verified=True)
        db_session.add(usuario)
        db_session.flush()
        db_session.add(UserBadge(user_id=usuario.id, badge_id=badge.id))
    db_session.commit()


def texto(resposta) -> str:
    return html.unescape(resposta.text)


def tag_das_regras(pagina: str) -> str:
    """A tag <fieldset> dos campos da regra (travada = tem "disabled")."""
    return re.search(r'<fieldset class="rule-fields"[^>]*>', pagina).group(0)


def recarregar(db_session, badge) -> Badge | None:
    db_session.expire_all()
    return db_session.get(Badge, badge.id)


def criar(client, arquivos=None, **campos):
    dados = {"name": "Explorador", "active": "true", **campos}
    return client.post(URL, data=dados, files=arquivos or {}, follow_redirects=False)


def salva(db_session, nome="Explorador") -> Badge:
    db_session.expire_all()
    return db_session.query(Badge).filter_by(name=nome).one()


# ---------- Lista ----------

def test_lista_vazia_avisa(client):
    pagina = client.get(URL)

    assert pagina.status_code == 200
    assert "Nenhuma insígnia cadastrada ainda." in pagina.text
    assert 'href="/admin/badges/new"' in pagina.text


def test_lista_mostra_tipo_condicao_situacao_e_conquistas(client, db_session, tema, insignia):
    db_session.add_all([
        Badge(name="Cinco pontos", rule_type=BadgeRule.VISIT_COUNT, required_count=5),
        Badge(name="Um Arte Deco", rule_type=BadgeRule.THEME_VISIT_COUNT,
              required_count=1, theme_id=tema.id, active=False),
    ])
    db_session.commit()
    conquistar(db_session, insignia, 2)

    pagina = texto(client.get(URL))

    linha = pagina[pagina.index("<strong>Visitou o Teatro</strong>"):]
    linha = linha[:linha.index("</tr>")]
    assert "Visita a ponto" in linha
    assert "Visitar Teatro Goiânia" in linha
    assert "Ativa" in linha
    assert "<td>2</td>" in linha
    assert f'href="/admin/badges/{insignia.id}/edit"' in linha

    assert "Visitar 5 pontos" in pagina
    assert "Quantidade geral" in pagina
    assert "Visitar 1 ponto de Arte Deco" in pagina
    assert "Desativada" in pagina


def test_lista_mostra_a_imagem(client, insignia):
    pagina = client.get(URL).text

    assert 'class="badge-thumb"' in pagina
    assert "badges/1/image-antiga.png" in pagina


def test_lista_escapa_html_do_nome(client, db_session):
    db_session.add(Badge(name="<b>x</b>", rule_type=BadgeRule.VISIT_COUNT, required_count=1))
    db_session.commit()

    assert "<b>x</b>" not in client.get(URL).text


# ---------- Formulário ----------

def test_formulario_tem_os_tres_tipos_e_os_campos(client, tema, teatro):
    pagina = client.get(f"{URL}/new").text

    for valor in ("point_visit", "visit_count", "theme_visit_count"):
        assert f'value="{valor}"' in pagina
    for campo in ("name", "description", "active", "image", "object_id", "theme_id", "required_count"):
        assert f'name="{campo}"' in pagina, campo
    assert "Teatro Goiânia" in pagina
    assert "Arte Deco" in pagina


def test_formulario_sem_temas_avisa(client):
    assert "Nenhum tema cadastrado" in client.get(f"{URL}/new").text


def test_formulario_marca_ponto_desativado(client, db_session, teatro):
    teatro.active = False
    db_session.commit()

    assert "Teatro Goiânia (desativado)" in client.get(f"{URL}/new").text


# ---------- Cadastro ----------

def test_cria_insignia_de_visita_e_volta_para_a_lista(client, db_session, teatro):
    resposta = criar(client, rule_type="point_visit", object_id=str(teatro.id))

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/admin/badges?msg=badge-created"
    badge = salva(db_session)
    assert (badge.rule_type, badge.object_id, badge.active) == (BadgeRule.POINT_VISIT, teatro.id, True)
    assert "Insígnia cadastrada." in client.get(resposta.headers["location"]).text


def test_cria_insignia_de_quantidade_geral(client, db_session, teatro):
    criar(client, rule_type="visit_count", required_count="5", object_id=str(teatro.id))

    badge = salva(db_session)
    # O ponto enviado é ignorado: só a regra escolhida vale
    assert (badge.required_count, badge.object_id, badge.theme_id) == (5, None, None)


def test_cria_insignia_por_tema(client, db_session, tema):
    criar(client, rule_type="theme_visit_count", required_count="3", theme_id=str(tema.id))

    badge = salva(db_session)
    assert (badge.rule_type, badge.required_count, badge.theme_id) == (
        BadgeRule.THEME_VISIT_COUNT, 3, tema.id,
    )


def test_cria_desativada(client, db_session):
    client.post(URL, data={"name": "Explorador", "rule_type": "visit_count", "required_count": "1"})

    assert salva(db_session).active is False


def test_cria_com_imagem_no_s3(client, db_session, s3_simulado):
    criar(client, {"image": ("i.png", PNG, "image/png")}, rule_type="visit_count", required_count="1")

    badge = salva(db_session)
    assert re.fullmatch(rf"badges/{badge.id}/image-[0-9a-f]{{32}}\.png", badge.image_key)
    assert chaves_no_bucket(s3_simulado) == [badge.image_key]


@pytest.mark.parametrize("campos, mensagem", [
    ({"name": "  "}, "Informe o nome da insígnia."),
    ({"name": "a" * 101}, "Nome: máximo de 100 caracteres."),
    ({"description": "x" * 2001, "rule_type": "visit_count", "required_count": "1"},
     "Descrição: máximo de 2000 caracteres."),
    ({"rule_type": "manual"}, "Escolha como a insígnia é conquistada."),
    ({"rule_type": "point_visit"}, "Selecione o ponto da insígnia."),
    ({"rule_type": "point_visit", "object_id": "999"}, "Ponto não encontrado."),
    ({"rule_type": "visit_count"}, "Informe a quantidade de pontos a visitar"),
    ({"rule_type": "visit_count", "required_count": "0"}, "Informe a quantidade de pontos a visitar"),
    ({"rule_type": "visit_count", "required_count": "dois"}, "Informe a quantidade de pontos a visitar"),
    ({"rule_type": "visit_count", "required_count": "1001"}, "Quantidade: no máximo 1000."),
    ({"rule_type": "theme_visit_count", "required_count": "2"}, "Selecione o tema."),
    ({"rule_type": "theme_visit_count", "required_count": "2", "theme_id": "999"}, "Tema não encontrado."),
])
def test_erros_voltam_ao_formulario_com_a_mensagem(client, db_session, campos, mensagem):
    resposta = criar(client, **campos)

    assert resposta.status_code == 400
    assert mensagem in texto(resposta)
    assert db_session.query(Badge).count() == 0


def test_erro_mantem_o_que_foi_digitado(client, teatro):
    resposta = criar(
        client, name="Explorador", description="Minha descrição",
        rule_type="theme_visit_count", required_count="4",
    )

    assert 'value="Explorador"' in resposta.text
    assert "Minha descrição</textarea>" in resposta.text
    assert 'value="theme_visit_count" selected' in resposta.text
    assert 'value="4"' in resposta.text
    assert "Se você tinha escolhido uma imagem, escolha de novo." in texto(resposta)


@pytest.mark.parametrize("repetido", ["Visitou o Teatro", "visitou o teatro"])
def test_nome_repetido(client, db_session, insignia, repetido):
    resposta = criar(client, name=repetido, rule_type="visit_count", required_count="1")

    assert resposta.status_code == 400
    assert "Já existe uma insígnia com esse nome." in texto(resposta)


def test_imagem_invalida_nao_cadastra(client, db_session, s3_simulado):
    resposta = criar(
        client, {"image": ("i.png", b"nao e imagem", "image/png")},
        rule_type="visit_count", required_count="1",
    )

    assert resposta.status_code == 400
    assert "Formato não suportado" in texto(resposta)
    assert db_session.query(Badge).count() == 0
    assert chaves_no_bucket(s3_simulado) == []


def test_imagem_grande_demais(client, db_session, monkeypatch):
    monkeypatch.setattr(admin_files, "MAX_IMAGE_BYTES", 5)

    resposta = criar(client, {"image": ("i.png", PNG, "image/png")}, rule_type="visit_count", required_count="1")

    assert resposta.status_code == 413


def test_falha_do_s3_nao_cadastra(client, db_session, monkeypatch):
    def falha(*_):
        raise storage_service.StorageError("fora do ar")

    monkeypatch.setattr(storage_service, "save", falha)

    resposta = criar(client, {"image": ("i.png", PNG, "image/png")}, rule_type="visit_count", required_count="1")

    assert resposta.status_code == 502
    db_session.expire_all()
    assert db_session.query(Badge).count() == 0


# ---------- Edição ----------

def editar(client, badge, arquivos=None, **campos):
    dados = {
        "name": badge.name,
        "description": badge.description or "",
        "rule_type": badge.rule_type.value,
        "object_id": str(badge.object_id or ""),
        "theme_id": str(badge.theme_id or ""),
        "required_count": str(badge.required_count or ""),
        "active": "true",
        **campos,
    }
    return client.post(f"{URL}/{badge.id}/edit", data=dados, files=arquivos or {}, follow_redirects=False)


def test_tela_de_edicao_vem_preenchida(client, insignia, teatro):
    pagina = client.get(f"{URL}/{insignia.id}/edit").text

    assert 'value="Visitou o Teatro"' in pagina
    assert "Você esteve lá</textarea>" in pagina
    assert 'value="point_visit" selected' in pagina
    assert f'value="{teatro.id}" selected' in pagina
    assert 'class="photo-preview"' in pagina
    assert 'name="remove_image"' in pagina
    # Ninguém conquistou: a regra pode mudar
    assert "disabled" not in tag_das_regras(pagina)


def test_editar_nome_descricao_e_ponto(client, db_session, insignia):
    outro = MupiObject(name="Museu", latitude=0, longitude=0)
    db_session.add(outro)
    db_session.commit()

    resposta = editar(client, insignia, name="Visitou", description="", object_id=str(outro.id))

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/admin/badges?msg=badge-updated"
    badge = recarregar(db_session, insignia)
    assert (badge.name, badge.description, badge.object_id) == ("Visitou", None, outro.id)


def test_trocar_o_tipo_de_insignia_nao_conquistada(client, db_session, insignia):
    editar(client, insignia, rule_type="visit_count", required_count="3")

    badge = recarregar(db_session, insignia)
    assert (badge.rule_type, badge.required_count, badge.object_id) == (BadgeRule.VISIT_COUNT, 3, None)


def test_insignia_conquistada_nao_muda_de_regra(client, db_session, insignia, teatro):
    conquistar(db_session, insignia)

    pagina = client.get(f"{URL}/{insignia.id}/edit").text
    resposta = editar(client, insignia, name="Novo nome", rule_type="visit_count", required_count="3")

    assert "a regra não" in pagina
    assert "disabled" in tag_das_regras(pagina)
    assert resposta.status_code == 303
    badge = recarregar(db_session, insignia)
    # O nome muda; a regra continua a mesma
    assert badge.name == "Novo nome"
    assert (badge.rule_type, badge.object_id, badge.required_count) == (
        BadgeRule.POINT_VISIT, teatro.id, None,
    )


def test_editar_para_nome_de_outra(client, db_session, insignia):
    db_session.add(Badge(name="Outra", rule_type=BadgeRule.VISIT_COUNT, required_count=1))
    db_session.commit()

    resposta = editar(client, insignia, name="outra")

    assert resposta.status_code == 400
    assert "Já existe uma insígnia com esse nome." in texto(resposta)
    assert recarregar(db_session, insignia).name == "Visitou o Teatro"


def test_desmarcar_ativa_desativa(client, db_session, insignia):
    editar(client, insignia, active="")

    assert recarregar(db_session, insignia).active is False


def test_substituir_a_imagem_apaga_a_anterior(client, db_session, s3_simulado, insignia):
    editar(client, insignia, {"image": ("n.png", PNG, "image/png")})

    badge = recarregar(db_session, insignia)
    assert badge.image_key != "badges/1/image-antiga.png"
    assert chaves_no_bucket(s3_simulado) == [badge.image_key]


def test_remover_a_imagem(client, db_session, s3_simulado, insignia):
    editar(client, insignia, remove_image="true")

    assert recarregar(db_session, insignia).image_key is None
    assert chaves_no_bucket(s3_simulado) == []


def test_editar_sem_mexer_na_imagem_mantem(client, db_session, s3_simulado, insignia):
    editar(client, insignia)

    assert recarregar(db_session, insignia).image_key == "badges/1/image-antiga.png"
    assert chaves_no_bucket(s3_simulado) == ["badges/1/image-antiga.png"]


def test_erro_na_edicao_nao_muda_nada(client, db_session, s3_simulado, insignia):
    resposta = editar(client, insignia, {"image": ("n.png", PNG, "image/png")}, name="")

    assert resposta.status_code == 400
    assert recarregar(db_session, insignia).name == "Visitou o Teatro"
    assert chaves_no_bucket(s3_simulado) == ["badges/1/image-antiga.png"]


def test_editar_inexistente_retorna_404(client):
    assert client.get(f"{URL}/999/edit").status_code == 404
    assert client.post(f"{URL}/999/edit", data={"name": "X"}).status_code == 404


# ---------- Ativar e desativar (ADM-08) ----------

def test_desativar_e_ativar(client, db_session, insignia):
    desativar = client.post(f"{URL}/{insignia.id}/status", data={"active": "false"}, follow_redirects=False)

    assert desativar.headers["location"] == "/admin/badges?msg=badge-deactivated"
    assert recarregar(db_session, insignia).active is False
    assert "Quem já tem continua com ela." in client.get(desativar.headers["location"]).text

    ativar = client.post(f"{URL}/{insignia.id}/status", data={"active": "true"}, follow_redirects=False)

    assert ativar.headers["location"] == "/admin/badges?msg=badge-activated"
    assert recarregar(db_session, insignia).active is True


def test_desativar_mantem_as_conquistas(client, db_session, insignia):
    conquistar(db_session, insignia, 2)

    client.post(f"{URL}/{insignia.id}/status", data={"active": "false"})

    db_session.expire_all()
    assert db_session.query(UserBadge).filter_by(badge_id=insignia.id).count() == 2


# ---------- Excluir (ADM-09) ----------

def test_confirmacao_nao_exclui(client, db_session, insignia):
    pagina = client.get(f"{URL}/{insignia.id}/delete")

    assert pagina.status_code == 200
    assert "A imagem é apagada do armazenamento." in pagina.text
    assert f'action="/admin/badges/{insignia.id}/delete"' in pagina.text
    assert recarregar(db_session, insignia) is not None


def test_excluir_insignia_nao_conquistada(client, db_session, s3_simulado, insignia, teatro):
    resposta = client.post(f"{URL}/{insignia.id}/delete", follow_redirects=False)

    assert resposta.headers["location"] == "/admin/badges?msg=badge-deleted"
    assert recarregar(db_session, insignia) is None
    assert chaves_no_bucket(s3_simulado) == []
    # O ponto continua
    assert db_session.get(MupiObject, teatro.id) is not None


@pytest.mark.parametrize("quantos, aviso", [
    (1, "1 usuário já conquistou esta insígnia."),
    (3, "3 usuários já conquistaram esta insígnia."),
])
def test_insignia_conquistada_nao_pode_ser_excluida(client, db_session, s3_simulado, insignia, quantos, aviso):
    conquistar(db_session, insignia, quantos)

    confirmacao = client.get(f"{URL}/{insignia.id}/delete").text
    resposta = client.post(f"{URL}/{insignia.id}/delete", follow_redirects=False)

    assert aviso in confirmacao
    assert "Excluir definitivamente" not in confirmacao
    # Oferece desativar
    assert f'action="/admin/badges/{insignia.id}/status"' in confirmacao
    assert resposta.status_code == 409
    assert recarregar(db_session, insignia) is not None
    assert chaves_no_bucket(s3_simulado) == ["badges/1/image-antiga.png"]


def test_excluir_inexistente_retorna_404(client):
    assert client.post(f"{URL}/999/delete").status_code == 404


# ---------- Rotas antigas ----------

def test_cadastro_nao_responde_mais_em_json(client, db_session):
    resposta = criar(client, rule_type="visit_count", required_count="1")

    assert resposta.status_code == 303
    assert "application/json" not in resposta.headers.get("content-type", "")
