"""Cadastro do ponto pelo painel com o novo modelo (PT-02 a PT-09, ADM-04)."""
import pytest

from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.mupi_object_section import MupiObjectSection
from app.model.mupi_object_video import MupiObjectVideo
from app.model.theme import Theme
from app.model.user import User
from app.service.badge_service import register_visit

ID = "dQw4w9WgXcQ"
ID_2 = "9bZkp7q19f0"


@pytest.fixture
def client(admin_client):
    """Todas as rotas deste arquivo são do painel: usa um admin logado."""
    return admin_client


URL = "/admin/mupi-objects"


@pytest.fixture
def tema(db_session):
    tema = Theme(name="Arte Deco")
    db_session.add(tema)
    db_session.commit()
    return tema


@pytest.fixture
def modernismo(db_session):
    tema = Theme(name="Modernismo")
    db_session.add(tema)
    db_session.commit()
    return tema


def dados_do_ponto(**extras):
    dados = {
        "name": "Edifício Exemplo",
        "latitude": "-23.5505",
        "longitude": "-46.6333",
        "active": "true",
    }
    dados.update(extras)
    return dados


def cadastrar_ponto(client, **extras):
    return client.post(URL, data=dados_do_ponto(**extras))


def ponto_salvo(db_session, resposta):
    db_session.expire_all()
    return db_session.get(MupiObject, resposta.json()["id"])


def nada_foi_criado(db_session):
    return (
        db_session.query(MupiObject).count() == 0
        and db_session.query(MupiObjectSection).count() == 0
        and db_session.query(MupiObjectVideo).count() == 0
    )


# ---------- Temas (PT-03) ----------

def test_varios_temas_sao_gravados(client, db_session, tema, modernismo):
    resposta = cadastrar_ponto(client, theme_ids=[str(tema.id), str(modernismo.id)])

    assert resposta.status_code == 200
    ponto = ponto_salvo(db_session, resposta)
    assert [t.name for t in ponto.themes] == ["Arte Deco", "Modernismo"]


def test_um_tema(client, db_session, tema):
    resposta = cadastrar_ponto(client, theme_ids=str(tema.id))

    assert [t.id for t in ponto_salvo(db_session, resposta).themes] == [tema.id]


def test_tema_repetido_vira_um_so(client, db_session, tema):
    resposta = cadastrar_ponto(client, theme_ids=[str(tema.id), str(tema.id)])

    assert resposta.status_code == 200
    assert len(ponto_salvo(db_session, resposta).themes) == 1


def test_sem_tema_o_ponto_fica_sem_tema(client, db_session):
    resposta = cadastrar_ponto(client)

    assert resposta.status_code == 200
    assert ponto_salvo(db_session, resposta).themes == []


def test_tema_inexistente_retorna_400_e_nao_cria_ponto(client, db_session, tema):
    resposta = cadastrar_ponto(client, theme_ids=[str(tema.id), "999"])

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Tema não encontrado."
    assert nada_foi_criado(db_session)


def test_tema_nao_numerico_e_recusado(client, db_session):
    resposta = cadastrar_ponto(client, theme_ids="abc")

    assert resposta.status_code == 422
    assert nada_foi_criado(db_session)


# ---------- Blocos de texto (PT-04) ----------

def test_blocos_sao_gravados_na_ordem_do_formulario(client, db_session):
    resposta = cadastrar_ponto(
        client,
        section_title=["História", "Arquitetura"],
        section_body=["Construído em 1937.", "Linha 1\r\nLinha 2"],
    )

    assert resposta.status_code == 200
    blocos = ponto_salvo(db_session, resposta).sections
    assert [(b.position, b.title, b.body) for b in blocos] == [
        (0, "História", "Construído em 1937."),
        (1, "Arquitetura", "Linha 1\nLinha 2"),  # quebra de linha mantida
    ]


def test_bloco_totalmente_vazio_e_ignorado(client, db_session):
    resposta = cadastrar_ponto(
        client,
        section_title=["", "História", "  "],
        section_body=["", "Texto", ""],
    )

    blocos = ponto_salvo(db_session, resposta).sections
    assert [(b.position, b.title) for b in blocos] == [(0, "História")]


@pytest.mark.parametrize("titulo, texto, mensagem", [
    ("", "Só texto", "Bloco 1: informe o título."),
    ("Só título", "", "Bloco 1: escreva o texto."),
    ("x" * 151, "Texto", "Bloco 1: o título tem no máximo 150 caracteres."),
    ("Título", "x" * 20_001, "Bloco 1: o texto tem no máximo 20000 caracteres."),
])
def test_bloco_invalido_retorna_400_e_nao_cria_nada(client, db_session, titulo, texto, mensagem):
    resposta = cadastrar_ponto(client, section_title=titulo, section_body=texto)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem
    assert nada_foi_criado(db_session)


# ---------- Vídeos (PT-07) ----------

def test_videos_guardam_so_o_id_na_ordem(client, db_session):
    resposta = cadastrar_ponto(
        client,
        video_url=[f"https://youtu.be/{ID}", f"https://www.youtube.com/shorts/{ID_2}"],
        video_title=["Visita guiada", ""],
    )

    assert resposta.status_code == 200
    videos = ponto_salvo(db_session, resposta).videos
    assert [(v.position, v.youtube_id, v.title) for v in videos] == [
        (0, ID, "Visita guiada"),
        (1, ID_2, None),
    ]


@pytest.mark.parametrize("link", ["https://vimeo.com/1234", "não é link", "https://youtube.com/watch"])
def test_link_que_nao_e_do_youtube_retorna_400(client, db_session, link):
    resposta = cadastrar_ponto(client, video_url=link)

    assert resposta.status_code == 400
    assert resposta.json()["detail"].startswith("Link de vídeo inválido")
    assert nada_foi_criado(db_session)


def test_titulo_de_video_sem_link_retorna_400(client, db_session):
    resposta = cadastrar_ponto(client, video_url="", video_title="Sem link")

    assert resposta.status_code == 400
    assert nada_foi_criado(db_session)


# ---------- Estabelecimento (PT-08) e "existe individualmente" (PT-09) ----------

def test_campos_de_estabelecimento(client, db_session):
    resposta = cadastrar_ponto(
        client,
        address="  Rua 1, 100  ",
        opening_hours="Seg a sex\n9h às 18h",
        accessibility="Rampa",
    )

    ponto = ponto_salvo(db_session, resposta)
    assert ponto.address == "Rua 1, 100"
    assert ponto.opening_hours == "Seg a sex\n9h às 18h"
    assert ponto.accessibility == "Rampa"


def test_campos_de_estabelecimento_vazios_ficam_nulos(client, db_session):
    resposta = cadastrar_ponto(client, address=" ", opening_hours="", accessibility="")

    ponto = ponto_salvo(db_session, resposta)
    assert (ponto.address, ponto.opening_hours, ponto.accessibility) == (None, None, None)


def test_endereco_longo_demais_retorna_400(client, db_session):
    resposta = cadastrar_ponto(client, address="x" * 301)

    assert resposta.status_code == 400
    assert nada_foi_criado(db_session)


def test_por_padrao_o_ponto_existe_individualmente(client, db_session):
    assert ponto_salvo(db_session, cadastrar_ponto(client)).standalone is True


def test_ponto_so_de_rota(client, db_session):
    resposta = cadastrar_ponto(client, route_only="true")

    assert ponto_salvo(db_session, resposta).standalone is False


def test_nome_so_com_espacos_retorna_400(client, db_session):
    resposta = cadastrar_ponto(client, name="   ")

    assert resposta.status_code == 400
    assert nada_foi_criado(db_session)


# ---------- Efeito nas insígnias ----------

def test_insignia_por_tema_e_concedida(client, db_session, tema, modernismo):
    insignia = Badge(
        name="Visitar 1 ponto Modernismo",
        rule_type=BadgeRule.THEME_VISIT_COUNT,
        required_count=1,
        theme_id=modernismo.id,
    )
    usuario = User(email="ana@exemplo.com", password_hash="hash")
    db_session.add_all([insignia, usuario])
    db_session.commit()

    resposta = cadastrar_ponto(client, theme_ids=[str(tema.id), str(modernismo.id)])
    ponto = ponto_salvo(db_session, resposta)

    nova_visita, ganhas = register_visit(db_session, usuario.id, ponto)

    assert nova_visita is True
    assert [g.badge_id for g in ganhas] == [insignia.id]


def test_ponto_de_outro_tema_nao_concede_a_insignia(client, db_session, tema, modernismo):
    insignia = Badge(
        name="Visitar 1 ponto Arte Deco",
        rule_type=BadgeRule.THEME_VISIT_COUNT,
        required_count=1,
        theme_id=tema.id,
    )
    usuario = User(email="ana@exemplo.com", password_hash="hash")
    db_session.add_all([insignia, usuario])
    db_session.commit()

    resposta = cadastrar_ponto(client, theme_ids=str(modernismo.id))
    ponto = ponto_salvo(db_session, resposta)

    _, ganhas = register_visit(db_session, usuario.id, ponto)

    assert ganhas == []
