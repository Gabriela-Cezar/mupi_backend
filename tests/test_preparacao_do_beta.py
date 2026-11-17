"""Preparação do beta: limite geral por usuário (INF-08) e boas práticas de
produção (INF-09)."""
import subprocess
import sys

import pytest

from app.core import dependencies
from app.core.security import create_access_token
from app.model.user import User
from main import docs_urls


@pytest.fixture
def limite_de_3(monkeypatch):
    monkeypatch.setattr(dependencies.app_request_limiter, "max_requests", 3)


# ---------- Limite geral por usuário (INF-08) ----------

def test_passar_do_limite_responde_429_com_a_espera(user_client, limite_de_3):
    for _ in range(3):
        assert user_client.get("/users/me").status_code == 200

    resposta = user_client.get("/users/me")

    assert resposta.status_code == 429
    assert resposta.json()["detail"].startswith("Muitas requisições em pouco tempo. Aguarde")
    assert 1 <= int(resposta.headers["Retry-After"]) <= 60


def test_o_limite_vale_para_todas_as_rotas_do_app_juntas(user_client, limite_de_3):
    assert user_client.get("/users/me").status_code == 200
    assert user_client.get("/routes").status_code == 200
    assert user_client.get("/users/me/visits").status_code == 200

    assert user_client.get("/routes").status_code == 429


def test_o_limite_e_por_usuario(client, db_session, usuario, limite_de_3):
    outro = User(email="outro@exemplo.com", password_hash="x", email_verified=True)
    db_session.add(outro)
    db_session.commit()

    def com_token(user):
        return {"Authorization": f"Bearer {create_access_token(user.id, user.token_version)}"}

    for _ in range(3):
        client.get("/users/me", headers=com_token(usuario))

    assert client.get("/users/me", headers=com_token(usuario)).status_code == 429
    assert client.get("/users/me", headers=com_token(outro)).status_code == 200


def test_sem_login_nao_conta_no_limite(client, user_client, limite_de_3):
    for _ in range(5):
        assert client.get("/users/me", headers={"Authorization": ""}).status_code == 401

    assert user_client.get("/users/me").status_code == 200


def test_o_limite_libera_depois_da_janela(user_client, monkeypatch):
    agora = [1000.0]
    limiter = dependencies.app_request_limiter
    monkeypatch.setattr(limiter, "max_requests", 1)
    monkeypatch.setattr(limiter, "clock", lambda: agora[0])

    user_client.get("/users/me")
    assert user_client.get("/users/me").status_code == 429

    agora[0] += 61

    assert user_client.get("/users/me").status_code == 200


def test_painel_nao_entra_no_limite_do_app(admin_client, limite_de_3):
    for _ in range(5):
        assert admin_client.get("/admin/routes").status_code == 200


# ---------- Documentação desligada (INF-09) ----------

@pytest.mark.parametrize("caminho", ["/docs", "/redoc", "/openapi.json"])
def test_documentacao_desligada_por_padrao(client, caminho):
    assert client.get(caminho).status_code == 404


def test_documentacao_ligada_so_com_api_docs():
    assert docs_urls(True) == {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    assert docs_urls(False) == {"docs_url": None, "redoc_url": None, "openapi_url": None}


# ---------- Configuração (INF-08, INF-09) ----------

def _subir_config(**env) -> subprocess.CompletedProcess:
    """Importa a configuração num processo à parte, com estas variáveis."""
    base = {
        "DATABASE_URL": "sqlite://",
        "RESEND_API_KEY": "x",
        "EMAIL_FROM": "x@x",
        "SECRET_KEY": "k" * 32,
        "PATH": "/usr/bin:/bin",
    }
    return subprocess.run(
        [sys.executable, "-c", "import app.core.config"],
        env={**base, **env},
        capture_output=True,
        text=True,
    )


def test_secret_key_curta_impede_o_servidor_de_subir():
    resultado = _subir_config(SECRET_KEY="curta-demais")

    assert resultado.returncode != 0
    assert "SECRET_KEY muito curta" in resultado.stderr


def test_secret_key_com_32_caracteres_sobe():
    assert _subir_config().returncode == 0


@pytest.mark.parametrize("valor", ["0", "-5", "muitas"])
def test_limite_por_minuto_invalido_impede_o_servidor_de_subir(valor):
    resultado = _subir_config(APP_REQUESTS_PER_MINUTE=valor)

    assert resultado.returncode != 0
    assert "APP_REQUESTS_PER_MINUTE" in resultado.stderr

