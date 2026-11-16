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
def ponto_do_edificio(db_session):
    ponto = MupiObject(name="Edifício", latitude=0, longitude=0)
    db_session.add(ponto)
    db_session.commit()
    return ponto


@pytest.fixture
def insignias(db_session, tema, ponto_do_edificio):
    manual = Badge(
        name="Visitou o Edifício",
        rule_type=BadgeRule.POINT_VISIT,
        object_id=ponto_do_edificio.id,
    )
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





# ---------- Página do formulário de ponto ----------

def test_formulario_de_ponto_tem_temas_para_marcar(client, tema):
    html = client.get("/admin/mupi-objects/new").text

    assert 'name="theme_ids"' in html
    assert f'value="{tema.id}"' in html
    assert "Arte Deco" in html


def test_formulario_de_ponto_tem_os_campos_novos(client):
    html = client.get("/admin/mupi-objects/new").text

    for campo in (
        "route_only", "section_title", "section_body", "video_url", "video_title",
        "address", "opening_hours", "accessibility", "photo",
    ):
        assert f'name="{campo}"' in html, campo


def test_formulario_de_ponto_nao_liga_insignias(client, insignias):
    html = client.get("/admin/mupi-objects/new").text

    assert 'name="badge_ids"' not in html


def test_edicao_do_ponto_mostra_as_insignias_dele(client, insignias, ponto_do_edificio):
    html = client.get(f"/admin/mupi-objects/{ponto_do_edificio.id}/edit").text

    assert "Visitou o Edifício" in html
    assert "Visitar 5 pontos" not in html


# ---------- Cadastro de ponto: insígnias são ligadas na insígnia ----------

def dados_do_ponto(**extras):
    dados = {
        "name": "Edifício Exemplo",
        "latitude": "-23.5505",
        "longitude": "-46.6333",
        "active": "true",
    }
    dados.update(extras)
    return dados


def test_ponto_ignora_insignias_enviadas_pelo_formulario(client, db_session, insignias):
    """A ligação é feita na insígnia; o formulário do ponto não a muda."""
    resposta = client.post(
        "/admin/mupi-objects",
        follow_redirects=False,
        data=dados_do_ponto(badge_ids=[str(insignias["manual"].id)]),
    )

    assert resposta.status_code == 303
    db_session.expire_all()
    novo = db_session.query(MupiObject).filter_by(name="Edifício Exemplo").one()
    assert novo.badges == []


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
        follow_redirects=False,
        data=dados_do_ponto(name="Unigoias"),
        files={"photo": CAMPO_DE_ARQUIVO_VAZIO},
    )

    assert resposta.status_code == 303
    ponto = ponto_salvo(db_session)
    assert ponto.name == "Unigoias"
    assert ponto.photo_key is None
    assert chaves_no_bucket(s3_simulado) == []


def test_ponto_sem_nenhum_campo_de_foto_e_salvo(client, db_session):
    resposta = client.post("/admin/mupi-objects", data=dados_do_ponto(), follow_redirects=False)

    assert resposta.status_code == 303
    assert ponto_salvo(db_session).photo_key is None


def test_foto_vai_para_o_s3_e_o_banco_guarda_so_a_chave(client, db_session, s3_simulado):
    resposta = client.post(
        "/admin/mupi-objects",
        follow_redirects=False,
        data=dados_do_ponto(),
        files={"photo": ("foto.png", PNG, "image/png")},
    )

    assert resposta.status_code == 303
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
        follow_redirects=False,
        data=dados_do_ponto(),
        files={"photo": ("foto.png", JPEG, "image/png")},
    )

    chave = ponto_salvo(db_session).photo_key
    assert chave.endswith(".jpg")
    assert s3_simulado.get_object(Bucket=BUCKET_DE_TESTE, Key=chave)["ContentType"] == "image/jpeg"


def test_arquivo_que_nao_e_imagem_e_recusado(client, db_session, s3_simulado):
    resposta = client.post(
        "/admin/mupi-objects",
        follow_redirects=False,
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
        follow_redirects=False,
        data=dados_do_ponto(),
        files={"photo": ("foto.png", PNG, "image/png")},
    )

    assert resposta.status_code == 503
    assert "S3_BUCKET" in resposta.text
    assert 'value="Edifício Exemplo"' in resposta.text  # o formulário volta preenchido
    assert db_session.query(MupiObject).count() == 0


def test_falha_do_s3_nao_salva_o_ponto(client, db_session, monkeypatch):
    def s3_fora_do_ar(*args, **kwargs):
        raise storage_service.StorageError("fora do ar")

    monkeypatch.setattr(storage_service, "save", s3_fora_do_ar)

    resposta = client.post(
        "/admin/mupi-objects",
        follow_redirects=False,
        data=dados_do_ponto(),
        files={"photo": ("foto.png", PNG, "image/png")},
    )

    assert resposta.status_code == 502
    assert "Não foi possível salvar o arquivo" in resposta.text
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
        follow_redirects=False,
        data=dados_do_ponto(
            name="Unigoias",
            description="",
            theme_id="",
            video_urls="",
            csrf_token=csrf,
        ),
        files={"photo": CAMPO_DE_ARQUIVO_VAZIO},
    )

    assert resposta.status_code == 303
    assert ponto_salvo(db_session).name == "Unigoias"
