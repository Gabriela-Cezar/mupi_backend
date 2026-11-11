import pytest

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.theme import Theme


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
def insignias(db_session, tema):
    manual = Badge(name="Visitou o Edifício", rule_type=BadgeRule.MANUAL)
    contagem = Badge(
        name="Visitar 5 pontos",
        rule_type=BadgeRule.VISIT_COUNT,
        required_count=5,
    )
    por_tema = Badge(
        name="Visitar 3 pontos Arte Deco",
        rule_type=BadgeRule.THEME_VISIT_COUNT,
        required_count=3,
        theme_id=tema.id,
    )
    db_session.add_all([manual, contagem, por_tema])
    db_session.commit()
    return {"manual": manual, "contagem": contagem, "por_tema": por_tema}


def criar_insignia(client, **campos):
    dados = {"name": "Insígnia de teste"}
    dados.update(campos)
    return client.post("/admin/badges", data=dados)


def insignia_salva(db_session, resposta):
    db_session.expire_all()
    return db_session.get(Badge, resposta.json()["id"])


# ---------- Página do formulário de insígnia ----------

def test_formulario_de_insignia_tem_os_tres_tipos_de_regra(client):
    html = client.get("/admin/badges").text

    assert 'name="rule_type"' in html
    assert 'value="manual"' in html
    assert 'value="visit_count"' in html
    assert 'value="theme_visit_count"' in html


def test_formulario_de_insignia_tem_quantidade_e_tema(client, tema):
    html = client.get("/admin/badges").text

    assert 'name="required_count"' in html
    assert 'name="theme_id"' in html
    assert f'<option value="{tema.id}">Arte Deco</option>' in html


def test_formulario_de_insignia_sem_temas_avisa(client):
    html = client.get("/admin/badges").text

    assert "Nenhum tema cadastrado" in html


# ---------- Página do formulário de ponto ----------

def test_formulario_de_ponto_tem_campo_de_tema(client, tema):
    html = client.get("/admin/mupi-objects").text

    assert 'name="theme_id"' in html
    assert '<option value="">Sem tema</option>' in html
    assert f'<option value="{tema.id}">Arte Deco</option>' in html


def test_formulario_de_ponto_lista_so_insignias_manuais(client, insignias):
    html = client.get("/admin/mupi-objects").text

    assert f'value="{insignias["manual"].id}"' in html
    assert "Visitou o Edifício" in html
    assert "Visitar 5 pontos" not in html
    assert "Visitar 3 pontos Arte Deco" not in html


# ---------- Cadastro de insígnia: regras válidas ----------

def test_cria_insignia_manual(client, db_session):
    resposta = criar_insignia(client, rule_type="manual")

    assert resposta.status_code == 200
    insignia = insignia_salva(db_session, resposta)
    assert insignia.rule_type == BadgeRule.MANUAL
    assert insignia.required_count is None
    assert insignia.theme_id is None


def test_insignia_manual_ignora_quantidade_e_tema(client, db_session, tema):
    resposta = criar_insignia(
        client, rule_type="manual", required_count="5", theme_id=str(tema.id)
    )

    assert resposta.status_code == 200
    insignia = insignia_salva(db_session, resposta)
    assert insignia.required_count is None
    assert insignia.theme_id is None


def test_sem_tipo_de_regra_cria_manual(client, db_session):
    resposta = criar_insignia(client)

    assert resposta.status_code == 200
    assert insignia_salva(db_session, resposta).rule_type == BadgeRule.MANUAL


def test_cria_insignia_de_contagem_geral(client, db_session):
    resposta = criar_insignia(
        client, rule_type="visit_count", required_count="5", theme_id=""
    )

    assert resposta.status_code == 200
    insignia = insignia_salva(db_session, resposta)
    assert insignia.rule_type == BadgeRule.VISIT_COUNT
    assert insignia.required_count == 5
    assert insignia.theme_id is None


def test_contagem_geral_ignora_tema(client, db_session, tema):
    resposta = criar_insignia(
        client, rule_type="visit_count", required_count="5", theme_id=str(tema.id)
    )

    assert resposta.status_code == 200
    assert insignia_salva(db_session, resposta).theme_id is None


def test_cria_insignia_de_contagem_por_tema(client, db_session, tema):
    resposta = criar_insignia(
        client,
        rule_type="theme_visit_count",
        required_count="3",
        theme_id=str(tema.id),
    )

    assert resposta.status_code == 200
    insignia = insignia_salva(db_session, resposta)
    assert insignia.rule_type == BadgeRule.THEME_VISIT_COUNT
    assert insignia.required_count == 3
    assert insignia.theme_id == tema.id


# ---------- Cadastro de insígnia: erros ----------

@pytest.mark.parametrize("quantidade", ["", "0", "-2"])
@pytest.mark.parametrize("regra", ["visit_count", "theme_visit_count"])
def test_contagem_exige_quantidade_minima_de_1(client, db_session, tema, regra, quantidade):
    resposta = criar_insignia(
        client, rule_type=regra, required_count=quantidade, theme_id=str(tema.id)
    )

    assert resposta.status_code == 400
    assert "quantidade" in resposta.json()["detail"]
    assert db_session.query(Badge).count() == 0


def test_quantidade_nao_numerica_retorna_400(client, db_session):
    resposta = criar_insignia(client, rule_type="visit_count", required_count="cinco")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Valor inválido para quantidade."
    assert db_session.query(Badge).count() == 0


@pytest.mark.parametrize("tema_informado", ["", "999"])
def test_contagem_por_tema_exige_tema_valido(client, db_session, tema_informado):
    resposta = criar_insignia(
        client,
        rule_type="theme_visit_count",
        required_count="3",
        theme_id=tema_informado,
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Selecione um tema válido para esta regra."
    assert db_session.query(Badge).count() == 0


def test_tipo_de_regra_invalido_retorna_400(client, db_session):
    resposta = criar_insignia(client, rule_type="qualquer_coisa")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Tipo de regra inválido."
    assert db_session.query(Badge).count() == 0


def test_nome_repetido_retorna_400(client, db_session):
    criar_insignia(client, name="Explorador")

    resposta = criar_insignia(client, name="Explorador")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Já existe uma insígnia com esse nome."
    assert db_session.query(Badge).count() == 1


# ---------- Cadastro de ponto: só insígnias manuais ----------

def dados_do_ponto(**extras):
    dados = {
        "name": "Edifício Exemplo",
        "latitude": "-23.5505",
        "longitude": "-46.6333",
        "active": "true",
    }
    dados.update(extras)
    return dados


def test_ponto_aceita_insignia_manual(client, db_session, insignias):
    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(badge_ids=[str(insignias["manual"].id)]),
    )

    assert resposta.status_code == 200
    db_session.expire_all()
    ponto = db_session.get(MupiObject, resposta.json()["id"])
    assert [b.id for b in ponto.badges] == [insignias["manual"].id]


@pytest.mark.parametrize("tipo", ["contagem", "por_tema"])
def test_ponto_recusa_insignia_de_contagem(client, db_session, insignias, tipo):
    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(badge_ids=[str(insignias[tipo].id)]),
    )

    assert resposta.status_code == 400
    assert "visitar este ponto" in resposta.json()["detail"]
    assert db_session.query(MupiObject).count() == 0


# ---------- Cadastro de ponto: campo de imagem como o navegador envia ----------

PNG = b"\x89PNG\r\n\x1a\n" + b"conteudo-da-imagem"
CAMPO_DE_ARQUIVO_VAZIO = ("", b"", "application/octet-stream")


def ponto_salvo(db_session):
    db_session.expire_all()
    return db_session.query(MupiObject).one()


def test_ponto_sem_imagem_e_salvo(client, db_session):
    """Sem imagem escolhida, o navegador envia o campo de arquivo vazio.

    Antes era recusado com 422 e o ponto não era salvo.
    """
    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(name="Unigoias"),
        files={"images": CAMPO_DE_ARQUIVO_VAZIO},
    )

    assert resposta.status_code == 200
    ponto = ponto_salvo(db_session)
    assert ponto.name == "Unigoias"
    assert ponto.media == []


def test_ponto_sem_nenhum_campo_de_imagem_e_salvo(client, db_session):
    resposta = client.post("/admin/mupi-objects", data=dados_do_ponto())

    assert resposta.status_code == 200
    assert ponto_salvo(db_session).media == []


def test_ponto_com_imagem_salva_a_imagem(client, db_session):
    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(),
        files={"images": ("foto.png", PNG, "image/png")},
    )

    assert resposta.status_code == 200
    [midia] = ponto_salvo(db_session).media
    assert midia.mime_type == "image/png"
    assert midia.title == "foto.png"


def test_imagem_vazia_entre_imagens_validas_e_ignorada(client, db_session):
    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(),
        files=[
            ("images", ("foto1.png", PNG, "image/png")),
            ("images", CAMPO_DE_ARQUIVO_VAZIO),
            ("images", ("foto2.png", PNG, "image/png")),
        ],
    )

    assert resposta.status_code == 200
    assert [m.title for m in ponto_salvo(db_session).media] == ["foto1.png", "foto2.png"]


def test_formulario_completo_como_o_navegador_envia(admin_client, db_session):
    """Token CSRF no campo escondido (não no cabeçalho), sem imagem e sem tema."""
    from tests.conftest import csrf_da_sessao

    csrf = admin_client.headers.pop("X-CSRF-Token")
    assert csrf == csrf_da_sessao(admin_client)

    resposta = admin_client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(
            name="Unigoias",
            description="",
            theme_id="",
            video_urls="",
            csrf_token=csrf,
        ),
        files={"images": CAMPO_DE_ARQUIVO_VAZIO},
    )

    assert resposta.status_code == 200
    assert ponto_salvo(db_session).name == "Unigoias"
