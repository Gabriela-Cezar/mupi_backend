"""Camada de arquivos no S3 (INF-04), com o S3 simulado pelo moto."""
from urllib.parse import parse_qs, urlparse

import pytest

from app.core import config
from app.service import storage_service
from tests.conftest import BUCKET_DE_TESTE, chaves_no_bucket


def test_salvar_guarda_o_arquivo_com_o_tipo(s3_simulado):
    storage_service.save("points/1/photo-x.png", b"conteudo", "image/png")

    arquivo = s3_simulado.get_object(Bucket=BUCKET_DE_TESTE, Key="points/1/photo-x.png")
    assert arquivo["Body"].read() == b"conteudo"
    assert arquivo["ContentType"] == "image/png"


@pytest.mark.parametrize("tipo, extensao", [
    ("image/png", "png"),
    ("image/jpeg", "jpg"),
    ("image/webp", "webp"),
    ("audio/mpeg", "mp3"),
    ("audio/mp4", "m4a"),
])
def test_chave_tem_pasta_nome_uuid_e_extensao(tipo, extensao):
    chave = storage_service.build_key("points/7", "photo", tipo)

    assert chave.startswith("points/7/photo-")
    assert chave.endswith("." + extensao)


def test_cada_envio_tem_uma_chave_nova():
    """Substituir a foto nunca devolve a antiga por causa de cache."""
    assert storage_service.build_key("points/7", "photo", "image/png") != \
        storage_service.build_key("points/7", "photo", "image/png")


def test_link_e_assinado_e_temporario():
    link = storage_service.url("points/1/photo-x.png", expires_in=3600)

    consulta = parse_qs(urlparse(link).query)
    assert consulta["X-Amz-Expires"] == ["3600"]
    assert "X-Amz-Signature" in consulta


def test_link_usa_o_endereco_regional_do_bucket():
    """Com o endereço global, a AWS redireciona e a assinatura deixa de valer."""
    link = storage_service.url("points/1/photo-x.png")

    partes = urlparse(link)
    assert partes.scheme == "https"
    assert partes.netloc == f"{BUCKET_DE_TESTE}.s3.sa-east-1.amazonaws.com"
    assert partes.path == "/points/1/photo-x.png"


def test_link_padrao_vale_24_horas():
    link = storage_service.url("points/1/photo-x.png")

    assert parse_qs(urlparse(link).query)["X-Amz-Expires"] == ["86400"]


def test_sem_chave_nao_ha_link():
    assert storage_service.url(None) is None
    assert storage_service.url("") is None


def test_link_e_reaproveitado_enquanto_vale_mais_da_metade(monkeypatch):
    agora = [1_000_000.0]
    monkeypatch.setattr(storage_service.time, "time", lambda: agora[0])

    cliente = storage_service._s3()
    gerados = []
    original = cliente.generate_presigned_url

    def contar_links(*args, **kwargs):
        gerados.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(cliente, "generate_presigned_url", contar_links)

    primeiro = storage_service.url("points/1/photo-x.png", expires_in=3600)

    agora[0] += 1799  # ainda vale mais da metade: mesmo link
    assert storage_service.url("points/1/photo-x.png", expires_in=3600) == primeiro
    assert len(gerados) == 1

    agora[0] += 2  # passou da metade: gera outro
    storage_service.url("points/1/photo-x.png", expires_in=3600)
    assert len(gerados) == 2


def test_apagar_remove_o_arquivo(s3_simulado):
    storage_service.save("badges/1/image-x.png", b"conteudo", "image/png")

    storage_service.delete("badges/1/image-x.png")

    assert chaves_no_bucket(s3_simulado) == []


def test_apagar_arquivo_que_nao_existe_nao_falha():
    storage_service.delete("points/1/nao-existe.png")
    storage_service.delete(None)


def test_sem_bucket_configurado(monkeypatch):
    monkeypatch.setattr(config, "S3_BUCKET", None)

    assert storage_service.is_configured() is False
    assert storage_service.url("points/1/photo-x.png") is None
    with pytest.raises(storage_service.StorageNotConfigured):
        storage_service.save("points/1/photo-x.png", b"x", "image/png")


def test_bucket_inexistente_vira_erro_de_armazenamento(monkeypatch):
    monkeypatch.setattr(config, "S3_BUCKET", "bucket-que-nao-existe")

    with pytest.raises(storage_service.StorageError):
        storage_service.save("points/1/photo-x.png", b"x", "image/png")
