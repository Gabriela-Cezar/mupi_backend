"""CORS: quais sites podem chamar a API pelo navegador (FAL-09)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.cors import (
    LOCAL_DEV_ORIGIN_REGEX,
    add_cors,
    parse_origins,
    validate_cors_settings,
)

SITE_MALICIOSO = "https://site-malicioso.com"
PAINEL = "https://painel.mupi.com.br"


def preflight(client, origem, path="/ping", headers="authorization"):
    """O pedido de permissão que o navegador faz antes de chamar outra origem."""
    return client.options(
        path,
        headers={
            "Origin": origem,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": headers,
        },
    )


def app_com_cors(origins=(), origin_regex=None) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    add_cors(app, list(origins), origin_regex)
    return TestClient(app)


def liberado(resposta, origem) -> bool:
    return resposta.headers.get("access-control-allow-origin") == origem


# ---------- A API de verdade (sem CORS configurado, como em produção) ----------

class TestApiSemCorsConfigurado:
    def test_site_de_fora_nao_recebe_permissao(self, client):
        resposta = preflight(client, SITE_MALICIOSO, "/mupi-objects")

        assert "access-control-allow-origin" not in resposta.headers

    def test_resposta_normal_nao_libera_site_de_fora(self, client):
        resposta = client.get("/mupi-objects", headers={"Origin": SITE_MALICIOSO})

        assert "access-control-allow-origin" not in resposta.headers

    def test_nunca_libera_envio_de_cookies(self, client):
        """Antes: allow_origins=['*'] com allow_credentials=True."""
        for path in ("/mupi-objects", "/admin/themes", "/auth/login"):
            resposta = preflight(client, SITE_MALICIOSO, path)
            assert "access-control-allow-credentials" not in resposta.headers

    def test_app_de_celular_continua_funcionando(self, client):
        """Pedidos sem Origin (app nativo) não são afetados pelo CORS."""
        resposta = client.post(
            "/auth/login", json={"email": "a@exemplo.com", "password": "x"}
        )

        assert resposta.status_code == 401  # chegou à rota normalmente


# ---------- Origens listadas ----------

class TestOrigensListadas:
    def test_origem_listada_e_liberada(self):
        client = app_com_cors([PAINEL])

        resposta = preflight(client, PAINEL)

        assert resposta.status_code == 200
        assert liberado(resposta, PAINEL)

    def test_outra_origem_nao_e_liberada(self):
        client = app_com_cors([PAINEL])

        assert not liberado(preflight(client, SITE_MALICIOSO), SITE_MALICIOSO)

    def test_subdominio_ou_protocolo_diferente_nao_e_liberado(self):
        client = app_com_cors([PAINEL])

        for origem in ("http://painel.mupi.com.br", "https://outro.mupi.com.br",
                       "https://painel.mupi.com.br.site-falso.com"):
            assert not liberado(preflight(client, origem), origem), origem

    def test_permite_o_cabecalho_do_token(self):
        client = app_com_cors([PAINEL])

        resposta = preflight(client, PAINEL, headers="authorization, content-type")

        permitidos = resposta.headers["access-control-allow-headers"].lower()
        assert "authorization" in permitidos
        assert "content-type" in permitidos

    def test_nao_libera_envio_de_cookies(self):
        client = app_com_cors([PAINEL])

        assert "access-control-allow-credentials" not in preflight(client, PAINEL).headers

    def test_o_app_no_navegador_pode_ler_o_retry_after(self):
        client = app_com_cors([PAINEL])

        resposta = client.get("/ping", headers={"Origin": PAINEL})

        assert liberado(resposta, PAINEL)
        assert "retry-after" in resposta.headers["access-control-expose-headers"].lower()


# ---------- Padrão para o desenvolvimento (Flutter web no Chrome) ----------

class TestPadraoDeDesenvolvimento:
    @pytest.mark.parametrize("origem", [
        "http://localhost:53421",
        "http://localhost:8080",
        "http://localhost",
        "http://127.0.0.1:61234",
    ])
    def test_localhost_em_qualquer_porta_e_liberado(self, origem):
        client = app_com_cors(origin_regex=LOCAL_DEV_ORIGIN_REGEX)

        assert liberado(preflight(client, origem), origem)

    @pytest.mark.parametrize("origem", [
        "http://localhost.site-falso.com",
        "http://localhost:8080.site-falso.com",
        "https://site-falso.com",
        "http://192.168.0.10:8080",
    ])
    def test_enderecos_parecidos_nao_sao_liberados(self, origem):
        client = app_com_cors(origin_regex=LOCAL_DEV_ORIGIN_REGEX)

        assert not liberado(preflight(client, origem), origem)


# ---------- Sem configuração ----------

def test_sem_configuracao_nenhum_site_e_liberado():
    client = app_com_cors()

    resposta = preflight(client, PAINEL)

    assert "access-control-allow-origin" not in resposta.headers


# ---------- Validação da configuração ----------

class TestValidacao:
    def test_asterisco_impede_o_servidor_de_subir(self):
        with pytest.raises(RuntimeError, match="não pode ser '\\*'"):
            validate_cors_settings(["*"], None)

    @pytest.mark.parametrize("origem", [
        "painel.mupi.com.br",          # sem protocolo
        "https://painel.mupi.com.br/",  # barra no final
        "ftp://painel.mupi.com.br",
    ])
    def test_origem_mal_formatada_impede_o_servidor_de_subir(self, origem):
        with pytest.raises(RuntimeError, match="Origem CORS inválida"):
            validate_cors_settings([origem], None)

    def test_padrao_invalido_impede_o_servidor_de_subir(self):
        with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGIN_REGEX inválido"):
            validate_cors_settings([], "^(sem-fechar")

    def test_configuracao_valida_passa(self):
        validate_cors_settings([PAINEL, "http://localhost:3000"], LOCAL_DEV_ORIGIN_REGEX)

    def test_add_cors_valida_antes_de_configurar(self):
        with pytest.raises(RuntimeError):
            add_cors(FastAPI(), ["*"], None)


@pytest.mark.parametrize("valor, esperado", [
    (None, []),
    ("", []),
    ("   ", []),
    (PAINEL, [PAINEL]),
    (f" {PAINEL} , http://localhost:3000 ,, ", [PAINEL, "http://localhost:3000"]),
])
def test_parse_origins(valor, esperado):
    assert parse_origins(valor) == esperado
