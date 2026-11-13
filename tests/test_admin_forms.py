import re

import pytest

from app.core import config
from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.theme import Theme
from app.service import storage_service
from tests.conftest import BUCKET_DE_TESTE, chaves_no_bucket


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


# ---------- Cadastro de ponto: foto enviada ao S3 (INF-04) ----------

PNG = b"\x89PNG\r\n\x1a\n" + b"conteudo-da-imagem"
JPEG = b"\xff\xd8\xff" + b"conteudo-da-imagem"
CAMPO_DE_ARQUIVO_VAZIO = ("", b"", "application/octet-stream")


def ponto_salvo(db_session):
    db_session.expire_all()
    return db_session.query(MupiObject).one()


def test_ponto_sem_foto_e_salvo(client, db_session, s3_simulado):
    """Sem foto escolhida, o navegador envia o campo de arquivo vazio.

    Antes era recusado com 422 e o ponto não era salvo.
    """
    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(name="Unigoias"),
        files={"photo": CAMPO_DE_ARQUIVO_VAZIO},
    )

    assert resposta.status_code == 200
    ponto = ponto_salvo(db_session)
    assert ponto.name == "Unigoias"
    assert ponto.photo_key is None
    assert chaves_no_bucket(s3_simulado) == []


def test_ponto_sem_nenhum_campo_de_foto_e_salvo(client, db_session):
    resposta = client.post("/admin/mupi-objects", data=dados_do_ponto())

    assert resposta.status_code == 200
    assert ponto_salvo(db_session).photo_key is None


def test_foto_vai_para_o_s3_e_o_banco_guarda_so_a_chave(client, db_session, s3_simulado):
    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(),
        files={"photo": ("foto.png", PNG, "image/png")},
    )

    assert resposta.status_code == 200
    ponto = ponto_salvo(db_session)
    assert re.fullmatch(rf"points/{ponto.id}/photo-[0-9a-f]{{32}}\.png", ponto.photo_key)
    assert chaves_no_bucket(s3_simulado) == [ponto.photo_key]

    arquivo = s3_simulado.get_object(Bucket=BUCKET_DE_TESTE, Key=ponto.photo_key)
    assert arquivo["Body"].read() == PNG
    assert arquivo["ContentType"] == "image/png"


def test_tipo_da_foto_vem_do_conteudo_e_nao_do_nome(client, db_session, s3_simulado):
    """Um JPEG chamado "foto.png" é guardado como JPEG."""
    client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(),
        files={"photo": ("foto.png", JPEG, "image/png")},
    )

    chave = ponto_salvo(db_session).photo_key
    assert chave.endswith(".jpg")
    assert s3_simulado.get_object(Bucket=BUCKET_DE_TESTE, Key=chave)["ContentType"] == "image/jpeg"


def test_arquivo_que_nao_e_imagem_e_recusado(client, db_session, s3_simulado):
    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(),
        files={"photo": ("foto.png", b"nao sou imagem", "image/png")},
    )

    assert resposta.status_code == 400
    assert db_session.query(MupiObject).count() == 0
    assert chaves_no_bucket(s3_simulado) == []


def test_sem_s3_configurado_a_foto_e_recusada_com_mensagem(client, db_session, monkeypatch):
    monkeypatch.setattr(config, "S3_BUCKET", None)

    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(),
        files={"photo": ("foto.png", PNG, "image/png")},
    )

    assert resposta.status_code == 503
    assert "S3_BUCKET" in resposta.json()["detail"]
    assert db_session.query(MupiObject).count() == 0


def test_falha_do_s3_nao_salva_o_ponto(client, db_session, monkeypatch):
    def s3_fora_do_ar(*args, **kwargs):
        raise storage_service.StorageError("fora do ar")

    monkeypatch.setattr(storage_service, "save", s3_fora_do_ar)

    resposta = client.post(
        "/admin/mupi-objects",
        data=dados_do_ponto(),
        files={"photo": ("foto.png", PNG, "image/png")},
    )

    assert resposta.status_code == 502
    assert db_session.query(MupiObject).count() == 0


def test_falha_no_banco_apaga_a_foto_ja_enviada(client, db_session, s3_simulado, monkeypatch):
    """Sem isso, ficaria no bucket um arquivo que nenhum ponto usa."""
    def commit_que_falha():
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(db_session, "commit", commit_que_falha)

    with pytest.raises(RuntimeError):
        client.post(
            "/admin/mupi-objects",
            data=dados_do_ponto(),
            files={"photo": ("foto.png", PNG, "image/png")},
        )

    assert chaves_no_bucket(s3_simulado) == []


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
        files={"photo": CAMPO_DE_ARQUIVO_VAZIO},
    )

    assert resposta.status_code == 200
    assert ponto_salvo(db_session).name == "Unigoias"


# ---------- Imagem da insígnia no S3 (INF-04) ----------

def test_imagem_da_insignia_vai_para_o_s3(client, db_session, s3_simulado):
    resposta = client.post(
        "/admin/badges",
        data={"name": "Explorador", "rule_type": "manual"},
        files={"image": ("insignia.png", PNG, "image/png")},
    )

    assert resposta.status_code == 200
    insignia = db_session.get(Badge, resposta.json()["id"])
    assert re.fullmatch(rf"badges/{insignia.id}/image-[0-9a-f]{{32}}\.png", insignia.image_key)
    assert chaves_no_bucket(s3_simulado) == [insignia.image_key]


def test_insignia_sem_imagem_nao_envia_nada(client, db_session, s3_simulado):
    resposta = client.post(
        "/admin/badges",
        data={"name": "Explorador", "rule_type": "manual"},
        files={"image": CAMPO_DE_ARQUIVO_VAZIO},
    )

    assert resposta.status_code == 200
    assert db_session.get(Badge, resposta.json()["id"]).image_key is None
    assert chaves_no_bucket(s3_simulado) == []


def test_insignia_com_nome_repetido_nao_envia_a_imagem(client, db_session, s3_simulado):
    client.post("/admin/badges", data={"name": "Explorador", "rule_type": "manual"})

    resposta = client.post(
        "/admin/badges",
        data={"name": "Explorador", "rule_type": "manual"},
        files={"image": ("insignia.png", PNG, "image/png")},
    )

    assert resposta.status_code == 400
    assert chaves_no_bucket(s3_simulado) == []
