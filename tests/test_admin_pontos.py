"""Pontos no painel: lista, edição, foto, ativar/desativar e exclusão
(ADM-04, ADM-08, ADM-09, ADM-12, PT-05)."""
import html

import pytest

from app.core import config
from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.mupi_object_section import MupiObjectSection
from app.model.mupi_object_video import MupiObjectVideo
from app.model.theme import Theme
from app.model.user import User
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit
from app.service import storage_service
from tests.conftest import BUCKET_DE_TESTE, chaves_no_bucket

URL = "/admin/mupi-objects"
PNG = b"\x89PNG\r\n\x1a\n" + b"foto-nova"
FOTO_ANTIGA = b"\x89PNG\r\n\x1a\n" + b"foto-antiga"
ID = "dQw4w9WgXcQ"
ID_2 = "9bZkp7q19f0"


@pytest.fixture
def client(admin_client):
    """Todas as rotas deste arquivo são do painel: usa um admin logado."""
    return admin_client


@pytest.fixture
def arte_deco(db_session):
    tema = Theme(name="Arte Deco")
    db_session.add(tema)
    db_session.commit()
    return tema


@pytest.fixture
def ponto(db_session, arte_deco, s3_simulado):
    """Ponto completo, com foto já no S3."""
    chave = "points/1/photo-antiga.png"
    s3_simulado.put_object(Bucket=BUCKET_DE_TESTE, Key=chave, Body=FOTO_ANTIGA)

    ponto = MupiObject(
        name="Edifício Exemplo",
        latitude=-16.68,
        longitude=-49.26,
        active=True,
        themes=[arte_deco],
        photo_key=chave,
        address="Rua 1",
        sections=[
            MupiObjectSection(position=0, title="História", body="Texto 1"),
            MupiObjectSection(position=1, title="Arquitetura", body="Texto 2"),
        ],
        videos=[MupiObjectVideo(position=0, youtube_id=ID, title="Visita")],
    )
    db_session.add(ponto)
    db_session.commit()
    return ponto


def recarregar(db_session, ponto) -> MupiObject:
    db_session.expire_all()
    return db_session.get(MupiObject, ponto.id)


def dados_completos(**extras):
    """O que o navegador envia ao salvar a edição sem mudar nada."""
    dados = {
        "name": "Edifício Exemplo",
        "latitude": "-16.68",
        "longitude": "-49.26",
        "active": "true",
        "section_title": ["História", "Arquitetura"],
        "section_body": ["Texto 1", "Texto 2"],
        "video_url": [f"https://www.youtube.com/watch?v={ID}"],
        "video_title": ["Visita"],
        "address": "Rua 1",
    }
    dados.update(extras)
    return dados


def editar(client, ponto, files=None, **extras):
    return client.post(
        f"{URL}/{ponto.id}/edit",
        data=dados_completos(**extras),
        files=files,
        follow_redirects=False,
    )


def salvou(resposta, codigo="point-updated"):
    assert resposta.status_code == 303, html.unescape(resposta.text)
    assert resposta.headers["location"] == f"{URL}?msg={codigo}"
    return True


def visitar(db_session, ponto):
    usuario = User(email="ana@exemplo.com", password_hash="x")
    db_session.add(usuario)
    db_session.commit()
    db_session.add(UserVisit(user_id=usuario.id, object_id=ponto.id))
    db_session.commit()
    return usuario


# ---------- Lista ----------

def test_lista_vazia(client):
    resposta = client.get(URL)

    assert resposta.status_code == 200
    assert "Nenhum ponto cadastrado ainda." in resposta.text
    assert f'href="{URL}/new"' in resposta.text


def test_lista_mostra_os_dados_de_cada_ponto(client, db_session, ponto):
    visitar(db_session, ponto)
    db_session.add(MupiObject(name="Praça", latitude=0, longitude=0, active=False, standalone=False))
    db_session.commit()

    pagina = client.get(URL).text

    assert pagina.index("Edifício Exemplo") < pagina.index("Praça")  # ordem alfabética
    linha = pagina[pagina.index("<strong>Edifício Exemplo</strong>"):]
    linha = linha[:linha.index("</tr>")]
    assert "Ativo" in linha
    assert "<td>Arte Deco</td>" in linha
    assert "<td>Sim</td>" in linha  # tem foto
    assert "<td>1</td>" in linha  # visitas
    assert f'href="{URL}/{ponto.id}/edit"' in linha
    assert f'href="{URL}/{ponto.id}/delete"' in linha

    praca = pagina[pagina.index("<strong>Praça</strong>"):]
    assert "Desativado" in praca
    assert "Só em rotas" in praca


def test_lista_escapa_html_do_nome(client, db_session):
    db_session.add(MupiObject(name="<script>x</script>", latitude=0, longitude=0))
    db_session.commit()

    pagina = client.get(URL).text

    assert "<script>x</script>" not in pagina
    assert "&lt;script&gt;" in pagina


def test_cadastro_volta_para_a_lista_com_mensagem(client):
    resposta = client.post(
        URL, data={"name": "Novo", "latitude": "0", "longitude": "0", "active": "true"},
    )

    assert resposta.status_code == 200
    assert str(resposta.url).endswith(f"{URL}?msg=point-created")
    assert "Ponto cadastrado." in resposta.text
    assert "<strong>Novo</strong>" in resposta.text


# ---------- Tela de edição ----------

def test_tela_de_edicao_vem_preenchida(client, ponto, arte_deco):
    resposta = client.get(f"{URL}/{ponto.id}/edit")

    assert resposta.status_code == 200
    pagina = resposta.text
    assert f'action="{URL}/{ponto.id}/edit"' in pagina
    assert 'value="Edifício Exemplo"' in pagina
    assert 'value="-16.68"' in pagina
    assert f'value="{arte_deco.id}"\n                                checked' in pagina
    assert 'value="História"' in pagina
    assert "Texto 2</textarea>" in pagina
    assert f'value="https://www.youtube.com/watch?v={ID}"' in pagina
    assert 'value="Rua 1"' in pagina
    assert 'name="remove_photo"' in pagina
    assert 'class="photo-preview"' in pagina
    assert "Salvar alterações" in pagina


def test_ponto_inexistente_retorna_404(client):
    assert client.get(f"{URL}/999/edit").status_code == 404
    assert client.post(f"{URL}/999/edit", data=dados_completos()).status_code == 404
    assert client.post(f"{URL}/999/status", data={"active": "false"}).status_code == 404
    assert client.get(f"{URL}/999/delete").status_code == 404


# ---------- Salvar a edição ----------

def test_editar_campos_simples_e_temas(client, db_session, ponto, arte_deco):
    modernismo = Theme(name="Modernismo")
    db_session.add(modernismo)
    db_session.commit()

    resposta = editar(
        client, ponto,
        name="Novo nome",
        latitude="-16,7",
        theme_ids=[str(modernismo.id)],
        address="",
        opening_hours="9h às 18h",
        route_only="true",
    )

    assert salvou(resposta)
    ponto = recarregar(db_session, ponto)
    assert ponto.name == "Novo nome"
    assert ponto.latitude == -16.7
    assert [t.name for t in ponto.themes] == ["Modernismo"]
    assert ponto.address is None
    assert ponto.opening_hours == "9h às 18h"
    assert ponto.standalone is False


def test_desmarcar_ativo_desativa(client, db_session, ponto):
    dados = dados_completos()
    del dados["active"]

    resposta = client.post(f"{URL}/{ponto.id}/edit", data=dados, follow_redirects=False)

    assert salvou(resposta)
    assert recarregar(db_session, ponto).active is False


def test_reordenar_editar_e_adicionar_blocos(client, db_session, ponto):
    resposta = editar(
        client, ponto,
        section_title=["Arquitetura", "História", "Curiosidades"],
        section_body=["Texto 2 revisto", "Texto 1", "Texto 3"],
    )

    assert salvou(resposta)
    blocos = recarregar(db_session, ponto).sections
    assert [(b.position, b.title, b.body) for b in blocos] == [
        (0, "Arquitetura", "Texto 2 revisto"),
        (1, "História", "Texto 1"),
        (2, "Curiosidades", "Texto 3"),
    ]


def test_remover_blocos(client, db_session, ponto):
    resposta = editar(client, ponto, section_title=["Arquitetura"], section_body=["Texto 2"])

    assert salvou(resposta)
    assert [(b.position, b.title) for b in recarregar(db_session, ponto).sections] == [
        (0, "Arquitetura"),
    ]
    assert db_session.query(MupiObjectSection).count() == 1


def test_remover_todos_os_blocos(client, db_session, ponto):
    resposta = editar(client, ponto, section_title=[], section_body=[])

    assert salvou(resposta)
    assert recarregar(db_session, ponto).sections == []


def test_reordenar_e_remover_videos(client, db_session, ponto):
    resposta = editar(
        client, ponto,
        video_url=[f"https://youtu.be/{ID_2}", f"https://youtu.be/{ID}"],
        video_title=["Novo", ""],
    )

    assert salvou(resposta)
    videos = recarregar(db_session, ponto).videos
    assert [(v.position, v.youtube_id, v.title) for v in videos] == [
        (0, ID_2, "Novo"), (1, ID, None),
    ]

    assert salvou(editar(client, ponto, video_url=[], video_title=[]))
    assert recarregar(db_session, ponto).videos == []
    assert db_session.query(MupiObjectVideo).count() == 0


def test_erro_na_edicao_nao_muda_nada_e_volta_preenchido(client, db_session, ponto):
    resposta = editar(client, ponto, name="Nome novo", video_url=["https://vimeo.com/1"])

    assert resposta.status_code == 400
    assert "Link de vídeo inválido" in html.unescape(resposta.text)
    assert 'value="Nome novo"' in resposta.text
    assert f'action="{URL}/{ponto.id}/edit"' in resposta.text
    ponto = recarregar(db_session, ponto)
    assert ponto.name == "Edifício Exemplo"
    assert len(ponto.videos) == 1


# ---------- Foto (PT-05) ----------

def test_salvar_sem_enviar_foto_mantem_a_atual(client, db_session, ponto, s3_simulado):
    chave = ponto.photo_key

    resposta = editar(client, ponto, files={"photo": ("", b"", "application/octet-stream")})

    assert salvou(resposta)
    assert recarregar(db_session, ponto).photo_key == chave
    assert chaves_no_bucket(s3_simulado) == [chave]


def test_substituir_a_foto_apaga_a_anterior(client, db_session, ponto, s3_simulado):
    antiga = ponto.photo_key

    resposta = editar(client, ponto, files={"photo": ("nova.png", PNG, "image/png")})

    assert salvou(resposta)
    nova = recarregar(db_session, ponto).photo_key
    assert nova != antiga
    assert nova.startswith(f"points/{ponto.id}/photo-")
    assert chaves_no_bucket(s3_simulado) == [nova]
    assert s3_simulado.get_object(Bucket=BUCKET_DE_TESTE, Key=nova)["Body"].read() == PNG


def test_remover_a_foto(client, db_session, ponto, s3_simulado):
    resposta = editar(client, ponto, remove_photo="true")

    assert salvou(resposta)
    assert recarregar(db_session, ponto).photo_key is None
    assert chaves_no_bucket(s3_simulado) == []


def test_foto_invalida_mantem_a_atual(client, db_session, ponto, s3_simulado):
    antiga = ponto.photo_key

    resposta = editar(client, ponto, files={"photo": ("x.png", b"nao e imagem", "image/png")})

    assert resposta.status_code == 400
    assert "Formato não suportado" in resposta.text
    assert recarregar(db_session, ponto).photo_key == antiga
    assert chaves_no_bucket(s3_simulado) == [antiga]


def test_falha_do_s3_na_edicao_nao_muda_nada(client, db_session, ponto, monkeypatch):
    def s3_fora_do_ar(*args, **kwargs):
        raise storage_service.StorageError("fora do ar")

    monkeypatch.setattr(storage_service, "save", s3_fora_do_ar)

    resposta = editar(client, ponto, name="Outro", files={"photo": ("n.png", PNG, "image/png")})

    assert resposta.status_code == 502
    assert recarregar(db_session, ponto).name == "Edifício Exemplo"


def test_sem_s3_a_tela_de_edicao_abre_sem_previa(client, ponto, monkeypatch):
    monkeypatch.setattr(config, "S3_BUCKET", None)

    resposta = client.get(f"{URL}/{ponto.id}/edit")

    assert resposta.status_code == 200
    assert 'class="photo-preview"' not in resposta.text


# ---------- Ativar e desativar (ADM-08) ----------

def test_desativar_e_ativar(client, db_session, ponto):
    resposta = client.post(f"{URL}/{ponto.id}/status", data={"active": "false"}, follow_redirects=False)

    assert salvou(resposta, "point-deactivated")
    assert recarregar(db_session, ponto).active is False

    resposta = client.post(f"{URL}/{ponto.id}/status", data={"active": "true"}, follow_redirects=False)

    assert salvou(resposta, "point-activated")
    assert recarregar(db_session, ponto).active is True


def test_desativar_mantem_o_historico(client, db_session, ponto):
    usuario = visitar(db_session, ponto)

    client.post(f"{URL}/{ponto.id}/status", data={"active": "false"})

    assert db_session.get(UserVisit, (usuario.id, ponto.id)) is not None


def test_ponto_desativado_some_do_app(client, user_client, ponto):
    client.post(f"{URL}/{ponto.id}/status", data={"active": "false"})

    assert user_client.get("/mupi-objects").json() == []


# ---------- Excluir (ADM-09) ----------

def test_confirmacao_nao_exclui_e_explica_o_que_sera_apagado(client, db_session, ponto):
    resposta = client.get(f"{URL}/{ponto.id}/delete")

    assert resposta.status_code == 200
    assert "Edifício Exemplo" in resposta.text
    assert "A foto é apagada do armazenamento." in resposta.text
    assert "Excluir definitivamente" in resposta.text
    assert recarregar(db_session, ponto) is not None


def test_excluir_ponto_sem_historico_apaga_tudo(client, db_session, ponto, arte_deco, s3_simulado):
    resposta = client.post(f"{URL}/{ponto.id}/delete", follow_redirects=False)

    assert salvou(resposta, "point-deleted")
    assert recarregar(db_session, ponto) is None
    assert db_session.query(MupiObjectSection).count() == 0
    assert db_session.query(MupiObjectVideo).count() == 0
    assert chaves_no_bucket(s3_simulado) == []
    # O tema continua
    assert db_session.get(Theme, arte_deco.id) is not None


def test_ponto_visitado_nao_pode_ser_excluido(client, db_session, ponto, s3_simulado):
    visitar(db_session, ponto)

    confirmacao = client.get(f"{URL}/{ponto.id}/delete")
    resposta = client.post(f"{URL}/{ponto.id}/delete", follow_redirects=False)

    assert "Não é possível excluir" in confirmacao.text
    assert "1 usuário já visitou este ponto." in confirmacao.text
    assert "Excluir definitivamente" not in confirmacao.text
    # Oferece desativar
    assert f'action="{URL}/{ponto.id}/status"' in confirmacao.text
    assert resposta.status_code == 409
    assert recarregar(db_session, ponto) is not None
    assert chaves_no_bucket(s3_simulado) == [ponto.photo_key]


def test_ponto_ligado_a_insignia_nao_pode_ser_excluido(client, db_session, ponto):
    ponto.badges.append(Badge(name="Visitou o Edifício", rule_type=BadgeRule.POINT_VISIT))
    db_session.commit()

    resposta = client.post(f"{URL}/{ponto.id}/delete", follow_redirects=False)

    assert resposta.status_code == 409
    assert "Visitou o Edifício" in resposta.text
    assert recarregar(db_session, ponto) is not None


def test_ponto_desativado_com_historico_nao_oferece_desativar_de_novo(client, db_session, ponto):
    visitar(db_session, ponto)
    ponto.active = False
    db_session.commit()

    confirmacao = client.get(f"{URL}/{ponto.id}/delete").text

    assert "Não é possível excluir" in confirmacao
    assert f'action="{URL}/{ponto.id}/status"' not in confirmacao


def test_insignia_ganha_no_ponto_nao_bloqueia_por_si_so(client, db_session):
    """collected_at_object_id é só informativo (SET NULL); quem bloqueia é a visita."""
    ponto = MupiObject(name="P", latitude=0, longitude=0)
    insignia = Badge(name="Primeira", rule_type=BadgeRule.VISIT_COUNT, required_count=1)
    usuario = User(email="b@exemplo.com", password_hash="x")
    db_session.add_all([ponto, insignia, usuario])
    db_session.commit()
    db_session.add(UserBadge(user_id=usuario.id, badge_id=insignia.id, collected_at_object_id=ponto.id))
    db_session.commit()

    resposta = client.post(f"{URL}/{ponto.id}/delete", follow_redirects=False)

    assert salvou(resposta, "point-deleted")
    db_session.expire_all()
    assert db_session.get(UserBadge, (usuario.id, insignia.id)).collected_at_object_id is None
