"""Script de verificação do bucket (python -m app.scripts.check_storage)."""
from app.scripts import check_storage
from tests.conftest import chaves_no_bucket


class Resposta:
    def __init__(self, status, conteudo=b""):
        self.status_code = status
        self.content = conteudo
        self.text = conteudo.decode()


def simular_s3_real(monkeypatch, assinado=200, publico=403):
    """O moto não exige assinatura; simula as respostas do S3 de verdade."""
    def get(url, **kwargs):
        if "X-Amz-Signature" in url:
            return Resposta(assinado, check_storage.CONTENT if assinado == 200 else b"erro")
        return Resposta(publico)

    monkeypatch.setattr(check_storage.requests, "get", get)


def test_bucket_correto_nao_tem_problemas(s3_simulado, monkeypatch):
    simular_s3_real(monkeypatch)

    assert check_storage.check() == []
    assert chaves_no_bucket(s3_simulado) == []  # o arquivo de teste é apagado


def test_bucket_publico_e_apontado(s3_simulado, monkeypatch):
    simular_s3_real(monkeypatch, publico=200)

    [problema] = check_storage.check()
    assert "privado" in problema


def test_link_assinado_recusado_e_apontado(s3_simulado, monkeypatch):
    simular_s3_real(monkeypatch, assinado=403)

    [problema] = check_storage.check()
    assert "s3:GetObject" in problema
    assert chaves_no_bucket(s3_simulado) == []


def test_bucket_inexistente_e_apontado(monkeypatch):
    monkeypatch.setattr(check_storage.config, "S3_BUCKET", "bucket-que-nao-existe")

    [problema] = check_storage.check()
    assert "s3:PutObject" in problema
