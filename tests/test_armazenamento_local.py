"""Arquivos numa pasta local, para desenvolver sem S3 (LOCAL_STORAGE_DIR)."""
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app.core import config
from app.scripts import check_storage, move_images_to_s3
from app.service import storage_service


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    """Liga a pasta local no lugar do S3."""
    monkeypatch.setattr(config, "S3_BUCKET", None)
    monkeypatch.setattr(config, "LOCAL_STORAGE_DIR", tmp_path)
    storage_service.reset()
    yield tmp_path
    storage_service.reset()


def assinatura(link: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(link).query).items()}


# ---------- Serviço ----------

def test_pasta_local_conta_como_configurado(pasta):
    assert storage_service.is_configured()
    assert storage_service.is_local()


def test_salvar_grava_o_arquivo_na_pasta(pasta):
    storage_service.save("points/1/photo-x.png", b"conteudo", "image/png")

    assert (pasta / "points" / "1" / "photo-x.png").read_bytes() == b"conteudo"


def test_apagar_remove_o_arquivo_e_nao_falha_se_ja_nao_existe(pasta):
    storage_service.save("points/1/photo-x.png", b"conteudo", "image/png")

    storage_service.delete("points/1/photo-x.png")
    storage_service.delete("points/1/photo-x.png")

    assert not (pasta / "points" / "1" / "photo-x.png").exists()


@pytest.mark.parametrize("chave", [
    "../fora.png",
    "points/../../fora.png",
    "/etc/passwd",
    "points//x.png",
    "points/./x.png",
    "",
])
def test_chave_que_sairia_da_pasta_e_recusada(pasta, chave):
    with pytest.raises(storage_service.StorageError):
        storage_service.save(chave, b"x", "image/png")

    assert list(pasta.iterdir()) == []


def test_link_e_relativo_assinado_e_temporario(pasta):
    antes = int(time.time())

    link = storage_service.url("points/1/photo-x.png", expires_in=3600)

    assert link.startswith("/local-files/points/1/photo-x.png?")
    params = assinatura(link)
    assert antes + 3600 <= int(params["expires"]) <= int(time.time()) + 3600
    assert params["signature"]


def test_sem_chave_nao_ha_link(pasta):
    assert storage_service.url(None) is None


def test_s3_e_pasta_local_juntos_impedem_o_servidor_de_subir(monkeypatch):
    import importlib

    monkeypatch.setenv("S3_BUCKET", "um-bucket")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", "arquivos_locais")

    try:
        with pytest.raises(RuntimeError, match="não os dois"):
            importlib.reload(config)
    finally:
        monkeypatch.setenv("S3_BUCKET", "mupi-testes")
        monkeypatch.setenv("LOCAL_STORAGE_DIR", "")
        importlib.reload(config)


# ---------- Rota que entrega os arquivos ----------

def test_link_assinado_entrega_o_arquivo_com_o_tipo(pasta, client):
    storage_service.save("points/1/photo-x.png", b"\x89PNG conteudo", "image/png")

    resposta = client.get(storage_service.url("points/1/photo-x.png"))

    assert resposta.status_code == 200
    assert resposta.content == b"\x89PNG conteudo"
    assert resposta.headers["content-type"] == "image/png"


def test_sem_assinatura_e_recusado(pasta, client):
    storage_service.save("points/1/photo-x.png", b"conteudo", "image/png")

    assert client.get("/local-files/points/1/photo-x.png").status_code == 403


def test_assinatura_de_outro_arquivo_e_recusada(pasta, client):
    storage_service.save("points/1/photo-x.png", b"conteudo", "image/png")
    storage_service.save("points/2/photo-y.png", b"outro", "image/png")
    params = assinatura(storage_service.url("points/1/photo-x.png"))

    resposta = client.get("/local-files/points/2/photo-y.png", params=params)

    assert resposta.status_code == 403


def test_link_vencido_e_recusado(pasta, client):
    storage_service.save("points/1/photo-x.png", b"conteudo", "image/png")
    vencido = int(time.time()) - 1
    params = {
        "expires": str(vencido),
        "signature": storage_service.local_signature("points/1/photo-x.png", vencido),
    }

    resposta = client.get("/local-files/points/1/photo-x.png", params=params)

    assert resposta.status_code == 403


def test_prazo_alterado_invalida_a_assinatura(pasta, client):
    storage_service.save("points/1/photo-x.png", b"conteudo", "image/png")
    params = assinatura(storage_service.url("points/1/photo-x.png"))
    params["expires"] = str(int(params["expires"]) + 999_999)

    resposta = client.get("/local-files/points/1/photo-x.png", params=params)

    assert resposta.status_code == 403


def test_arquivo_apagado_responde_404(pasta, client):
    storage_service.save("points/1/photo-x.png", b"conteudo", "image/png")
    link = storage_service.url("points/1/photo-x.png")
    storage_service.delete("points/1/photo-x.png")

    assert client.get(link).status_code == 404


def test_com_s3_a_rota_nao_existe(client):
    """No S3 (produção) a pasta local nunca é servida."""
    assert client.get("/local-files/points/1/photo-x.png").status_code == 404


# ---------- Painel e app usando a pasta local ----------

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_foto_cadastrada_no_painel_vai_para_a_pasta_e_abre_pelo_link(
    pasta, admin_client, db_session
):
    from app.model.mupi_object import MupiObject

    resposta = admin_client.post(
        "/admin/mupi-objects",
        data={"name": "Teatro", "latitude": "-16.68", "longitude": "-49.26"},
        files={"photo": ("foto.png", PNG, "image/png")},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    ponto = db_session.query(MupiObject).one()
    assert (pasta / ponto.photo_key).read_bytes() == PNG

    foto = admin_client.get(storage_service.url(ponto.photo_key))
    assert foto.status_code == 200
    assert foto.content == PNG


# ---------- Scripts ----------

def test_check_storage_funciona_com_a_pasta_local(pasta, client, monkeypatch):
    """O script baixa pelo backend; aqui o backend é o cliente de teste."""
    monkeypatch.setattr(
        check_storage.requests, "get",
        lambda link, **_: client.get(link),
    )

    assert check_storage.check() == []
    # O arquivo de teste foi apagado
    assert not any(p.is_file() for p in pasta.rglob("*"))


def test_scripts_aceitam_a_pasta_local(pasta, monkeypatch, capsys):
    """Sem S3, o script de migração das imagens não recusa a pasta local."""
    monkeypatch.setattr(move_images_to_s3, "blobs_still_in_database", lambda: False)

    move_images_to_s3.main()

    assert "Nada a fazer" in capsys.readouterr().out
