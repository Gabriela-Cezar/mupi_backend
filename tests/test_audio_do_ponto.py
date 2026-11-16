"""Áudio do ponto (PT-06): formato pelo conteúdo, duração, painel e app."""
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.controller import admin_files
from app.core import config
from app.core.file_types import audio_duration_seconds, sniff_audio_mime
from app.core.templates import format_duration
from app.model.mupi_object import MupiObject
from app.service import storage_service
from tests.conftest import BUCKET_DE_TESTE, chaves_no_bucket

FIXTURES = Path(__file__).parent / "fixtures"
MP3 = (FIXTURES / "silencio_2s.mp3").read_bytes()
MP3_SEM_ID3 = (FIXTURES / "silencio_2s_sem_id3.mp3").read_bytes()
M4A = (FIXTURES / "silencio_2s.m4a").read_bytes()
VIDEO_MP4 = (FIXTURES / "video_1s.mp4").read_bytes()
PNG = b"\x89PNG\r\n\x1a\n" + b"foto"

URL = "/admin/mupi-objects"
LAT, LNG = -16.68, -49.26


# ---------- Formato pelo conteúdo e duração ----------

@pytest.mark.parametrize("dados, tipo", [
    (MP3, "audio/mpeg"),
    (MP3_SEM_ID3, "audio/mpeg"),
    (M4A, "audio/mp4"),
])
def test_reconhece_mp3_e_m4a_pelo_conteudo(dados, tipo):
    assert sniff_audio_mime(dados) == tipo


@pytest.mark.parametrize("dados", [
    VIDEO_MP4,                    # MP4 com vídeo não é áudio
    PNG,
    b"",
    b"texto qualquer",
    b"\xff\xff\xff\xff",          # parece sincronismo MPEG, mas é inválido
    b"RIFF\x00\x00\x00\x00WAVE",  # WAV não é aceito
])
def test_recusa_outros_conteudos(dados):
    assert sniff_audio_mime(dados) is None


@pytest.mark.parametrize("dados, tipo", [
    (MP3, "audio/mpeg"),
    (MP3_SEM_ID3, "audio/mpeg"),
    (M4A, "audio/mp4"),
])
def test_le_a_duracao_em_segundos(dados, tipo):
    assert audio_duration_seconds(dados, tipo) == 2


@pytest.mark.parametrize("dados, tipo", [
    (b"ID3" + b"\x00" * 200, "audio/mpeg"),   # só a etiqueta, sem áudio
    (M4A[:100], "audio/mp4"),                 # arquivo cortado
])
def test_arquivo_corrompido_nao_tem_duracao(dados, tipo):
    assert audio_duration_seconds(dados, tipo) is None


@pytest.mark.parametrize("segundos, texto", [
    (None, "—"), (0, "0:00"), (2, "0:02"), (125, "2:05"), (600, "10:00"),
])
def test_duracao_no_painel(segundos, texto):
    assert format_duration(segundos) == texto


# ---------- Painel ----------

@pytest.fixture
def client(admin_client):
    return admin_client


def campos(**extras):
    return {"name": "Teatro", "latitude": str(LAT), "longitude": str(LNG), "active": "true", **extras}


def cadastrar(client, arquivos):
    return client.post(URL, data=campos(), files=arquivos, follow_redirects=False)


def ponto_salvo(db_session) -> MupiObject:
    db_session.expire_all()
    return db_session.query(MupiObject).one()


def tipo_no_s3(s3, chave):
    return s3.head_object(Bucket=BUCKET_DE_TESTE, Key=chave)["ContentType"]


@pytest.mark.parametrize("nome, dados, extensao, tipo", [
    ("narracao.mp3", MP3, ".mp3", "audio/mpeg"),
    ("narracao.m4a", M4A, ".m4a", "audio/mp4"),
])
def test_cadastro_com_audio_guarda_no_s3_com_a_duracao(
    client, db_session, s3_simulado, nome, dados, extensao, tipo
):
    resposta = cadastrar(client, {"audio": (nome, dados, "application/octet-stream")})

    assert resposta.status_code == 303
    ponto = ponto_salvo(db_session)
    assert ponto.audio_key.startswith(f"points/{ponto.id}/audio-")
    assert ponto.audio_key.endswith(extensao)
    assert ponto.audio_duration == 2
    assert chaves_no_bucket(s3_simulado) == [ponto.audio_key]
    # O tipo vem do conteúdo, não do que o navegador declarou
    assert tipo_no_s3(s3_simulado, ponto.audio_key) == tipo


def test_cadastro_com_foto_e_audio(client, db_session, s3_simulado):
    cadastrar(client, {
        "photo": ("foto.png", PNG, "image/png"),
        "audio": ("narracao.mp3", MP3, "audio/mpeg"),
    })

    ponto = ponto_salvo(db_session)
    assert chaves_no_bucket(s3_simulado) == sorted([ponto.photo_key, ponto.audio_key])


def test_cadastro_sem_audio_continua_funcionando(client, db_session):
    assert cadastrar(client, {}).status_code == 303
    assert ponto_salvo(db_session).audio_key is None


@pytest.mark.parametrize("nome, dados, mensagem", [
    ("foto.mp3", PNG, "Formato de áudio não suportado (use MP3 ou M4A): foto.mp3"),
    ("video.m4a", VIDEO_MP4, "Formato de áudio não suportado (use MP3 ou M4A): video.m4a"),
    ("quebrado.mp3", b"ID3" + b"\x00" * 200, "Não foi possível ler o áudio (arquivo corrompido?): quebrado.mp3"),
])
def test_audio_invalido_nao_cadastra_nada(client, db_session, s3_simulado, nome, dados, mensagem):
    resposta = cadastrar(client, {
        "photo": ("foto.png", PNG, "image/png"),
        "audio": (nome, dados, "audio/mpeg"),
    })

    assert resposta.status_code == 400
    assert mensagem in resposta.text
    # O formulário volta com o que foi digitado e o aviso para escolher de novo
    assert 'value="Teatro"' in resposta.text
    assert "Se você tinha escolhido um áudio, escolha de novo." in resposta.text
    db_session.expire_all()
    assert db_session.query(MupiObject).count() == 0
    assert chaves_no_bucket(s3_simulado) == []


def test_audio_grande_demais_retorna_413(client, db_session, monkeypatch):
    monkeypatch.setattr(admin_files, "MAX_AUDIO_BYTES", 1000)

    resposta = cadastrar(client, {"audio": ("longo.mp3", MP3, "audio/mpeg")})

    assert resposta.status_code == 413
    assert "Áudio muito grande (máximo de 20 MB)" in resposta.text


def test_falha_no_envio_do_audio_apaga_a_foto_ja_enviada(client, db_session, s3_simulado, monkeypatch):
    original = storage_service.save

    def save_que_falha_no_audio(key, data, content_type):
        if "/audio-" in key:
            raise storage_service.StorageError("fora do ar")
        return original(key, data, content_type)

    monkeypatch.setattr(storage_service, "save", save_que_falha_no_audio)

    resposta = cadastrar(client, {
        "photo": ("foto.png", PNG, "image/png"),
        "audio": ("narracao.mp3", MP3, "audio/mpeg"),
    })

    assert resposta.status_code == 502
    db_session.expire_all()
    assert db_session.query(MupiObject).count() == 0
    # A foto que chegou a ir para o S3 não fica órfã
    assert chaves_no_bucket(s3_simulado) == []


@pytest.fixture
def ponto_com_audio(db_session, s3_simulado):
    chave = "points/1/audio-antigo.mp3"
    s3_simulado.put_object(Bucket=BUCKET_DE_TESTE, Key=chave, Body=MP3)

    ponto = MupiObject(
        name="Teatro", latitude=LAT, longitude=LNG,
        audio_key=chave, audio_duration=125,
    )
    db_session.add(ponto)
    db_session.commit()
    return ponto


def editar(client, ponto, arquivos=None, **extras):
    return client.post(
        f"{URL}/{ponto.id}/edit",
        data=campos(**extras),
        files=arquivos or {},
        follow_redirects=False,
    )


def test_edicao_mostra_o_audio_atual(client, ponto_com_audio):
    pagina = client.get(f"{URL}/{ponto_com_audio.id}/edit").text

    assert "<audio controls" in pagina
    assert "Duração: 2:05" in pagina
    assert "Substituir o áudio" in pagina
    assert 'name="remove_audio"' in pagina


def test_cadastro_novo_nao_mostra_opcoes_de_audio_atual(client):
    pagina = client.get(f"{URL}/new").text

    assert 'name="audio"' in pagina
    assert "<audio controls" not in pagina
    assert 'name="remove_audio"' not in pagina


def test_editar_sem_enviar_audio_mantem_o_atual(client, db_session, s3_simulado, ponto_com_audio):
    editar(client, ponto_com_audio)

    ponto = ponto_salvo(db_session)
    assert ponto.audio_key == "points/1/audio-antigo.mp3"
    assert ponto.audio_duration == 125
    assert chaves_no_bucket(s3_simulado) == ["points/1/audio-antigo.mp3"]


def test_substituir_o_audio_apaga_o_anterior(client, db_session, s3_simulado, ponto_com_audio):
    resposta = editar(client, ponto_com_audio, {"audio": ("novo.m4a", M4A, "audio/mp4")})

    assert resposta.status_code == 303
    ponto = ponto_salvo(db_session)
    assert ponto.audio_key.endswith(".m4a")
    assert ponto.audio_duration == 2
    assert chaves_no_bucket(s3_simulado) == [ponto.audio_key]


def test_remover_o_audio(client, db_session, s3_simulado, ponto_com_audio):
    editar(client, ponto_com_audio, remove_audio="true")

    ponto = ponto_salvo(db_session)
    assert ponto.audio_key is None
    assert ponto.audio_duration is None
    assert chaves_no_bucket(s3_simulado) == []


def test_enviar_e_marcar_remover_fica_com_o_novo(client, db_session, s3_simulado, ponto_com_audio):
    editar(client, ponto_com_audio, {"audio": ("novo.mp3", MP3, "audio/mpeg")}, remove_audio="true")

    ponto = ponto_salvo(db_session)
    assert ponto.audio_key is not None
    assert chaves_no_bucket(s3_simulado) == [ponto.audio_key]


def test_audio_invalido_na_edicao_nao_muda_nada(client, db_session, s3_simulado, ponto_com_audio):
    resposta = editar(client, ponto_com_audio, {"audio": ("x.mp3", PNG, "audio/mpeg")})

    assert resposta.status_code == 400
    ponto = ponto_salvo(db_session)
    assert ponto.audio_key == "points/1/audio-antigo.mp3"
    assert chaves_no_bucket(s3_simulado) == ["points/1/audio-antigo.mp3"]


def test_lista_mostra_a_duracao_do_audio(client, ponto_com_audio):
    pagina = client.get(URL).text

    assert "<th scope=\"col\">Áudio</th>" in pagina
    assert "<td>2:05</td>" in pagina


def test_excluir_o_ponto_apaga_o_audio(client, db_session, s3_simulado, ponto_com_audio):
    confirmacao = client.get(f"{URL}/{ponto_com_audio.id}/delete").text
    resposta = client.post(f"{URL}/{ponto_com_audio.id}/delete", follow_redirects=False)

    assert "O áudio é apagado do armazenamento." in confirmacao
    assert resposta.status_code == 303
    assert chaves_no_bucket(s3_simulado) == []


# ---------- App ----------

def test_resumo_indica_que_o_ponto_tem_audio(user_client, ponto_com_audio):
    [item] = user_client.get("/mupi-objects").json()

    assert item["has_audio"] is True
    # O link do áudio só vem na abertura
    assert "audio" not in item


def test_abertura_entrega_o_link_temporario_e_a_duracao(user_client, ponto_com_audio):
    resposta = user_client.post(
        f"/mupi-objects/{ponto_com_audio.id}/open",
        json={"latitude": LAT, "longitude": LNG},
    )

    audio = resposta.json()["audio"]
    assert audio["duration_seconds"] == 125
    link = urlparse(audio["url"])
    assert link.path.endswith("/points/1/audio-antigo.mp3")
    # Válido por 1 hora (AUDIO_URL_SECONDS)
    assert parse_qs(link.query)["X-Amz-Expires"] == ["3600"]


def test_ponto_sem_audio_vem_com_audio_nulo(user_client, db_session):
    ponto = MupiObject(name="Sem áudio", latitude=LAT, longitude=LNG)
    db_session.add(ponto)
    db_session.commit()

    dados = user_client.post(
        f"/mupi-objects/{ponto.id}/open", json={"latitude": LAT, "longitude": LNG}
    ).json()

    assert dados["audio"] is None
    assert dados["has_audio"] is False


# ---------- Requisições parciais (Range) ----------

def test_pasta_local_entrega_pedaco_do_audio(client, tmp_path, monkeypatch):
    """O player pede pedaços do arquivo para começar a tocar logo e avançar."""
    monkeypatch.setattr(config, "S3_BUCKET", None)
    monkeypatch.setattr(config, "LOCAL_STORAGE_DIR", tmp_path)
    storage_service.reset()
    storage_service.save("points/1/audio-x.mp3", MP3, "audio/mpeg")

    link = storage_service.url("points/1/audio-x.mp3", storage_service.AUDIO_URL_SECONDS)
    resposta = client.get(link, headers={"Range": "bytes=0-99"})

    assert resposta.status_code == 206
    assert resposta.content == MP3[:100]
    assert resposta.headers["content-type"] == "audio/mpeg"
    assert resposta.headers["content-range"] == f"bytes 0-99/{len(MP3)}"
    storage_service.reset()
