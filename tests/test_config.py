"""Configurações lidas num lugar só: app/core/config.py (FAL-18)."""
import re
from pathlib import Path

import pytest

from app.controller import mupi_object_controller
from app.core import config

RAIZ = Path(__file__).resolve().parent.parent

LAT, LNG = -16.6857, -49.2462
LONGE = {"latitude": LAT - 0.01, "longitude": LNG}


# ---------- Ninguém lê variáveis de ambiente fora do config.py ----------

def arquivos_python():
    pastas = [RAIZ / "app", RAIZ / "migrations"]
    arquivos = [RAIZ / "main.py"]
    for pasta in pastas:
        arquivos += sorted(pasta.rglob("*.py"))
    return [a for a in arquivos if a != RAIZ / "app/core/config.py"]


@pytest.mark.parametrize("arquivo", arquivos_python(), ids=lambda a: str(a.relative_to(RAIZ)))
def test_variaveis_de_ambiente_so_sao_lidas_no_config(arquivo):
    codigo = arquivo.read_text(encoding="utf-8")

    proibidos = re.findall(r"os\.getenv|os\.environ|load_dotenv|getenv\(", codigo)

    assert proibidos == [], (
        f"{arquivo.name} lê variável de ambiente direto; "
        "coloque a configuração em app/core/config.py"
    )


def test_a_rota_a_pe_usa_a_chave_do_config():
    assert "OPENROUTESERVICE_API_KEY" in vars(config)
    assert "os.getenv" not in (RAIZ / "app/controller/mupi_object_controller.py").read_text()


# ---------- Leitura das variáveis ----------

def test_obrigatoria_presente(monkeypatch):
    monkeypatch.setenv("MUPI_TESTE", "valor")

    assert config._require("MUPI_TESTE") == "valor"


@pytest.mark.parametrize("valor", [None, ""])
def test_obrigatoria_ausente_impede_o_servidor_de_subir(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("MUPI_TESTE", raising=False)
    else:
        monkeypatch.setenv("MUPI_TESTE", valor)

    with pytest.raises(RuntimeError, match="MUPI_TESTE"):
        config._require("MUPI_TESTE")


@pytest.mark.parametrize("valor, esperado", [
    (None, None),          # não existe no .env
    ("", None),            # existe, mas vazia
    ("   ", None),         # só espaços
    ("abc123", "abc123"),
    ("  abc123 \n", "abc123"),  # espaços sobrando no .env não estragam a chave
])
def test_opcional(monkeypatch, valor, esperado):
    if valor is None:
        monkeypatch.delenv("MUPI_TESTE", raising=False)
    else:
        monkeypatch.setenv("MUPI_TESTE", valor)

    assert config._optional("MUPI_TESTE") == esperado


# ---------- Rota a pé com e sem a chave ----------

class RespostaFalsa:
    status_code = 200
    text = ""

    def json(self):
        return {"routes": [{
            "geometry": "_p~iF~ps|U_ulLnnqC",
            "summary": {"distance": 100.0, "duration": 70.0},
        }]}


@pytest.fixture
def ponto(db_session):
    from app.model.mupi_object import MupiObject

    mupi = MupiObject(name="Ponto", latitude=LAT, longitude=LNG)
    db_session.add(mupi)
    db_session.commit()
    return mupi


def test_sem_chave_a_rota_explica_o_problema_e_nao_chama_o_servico(user_client, ponto, monkeypatch):
    chamadas = []
    monkeypatch.setattr(mupi_object_controller, "OPENROUTESERVICE_API_KEY", None)
    monkeypatch.setattr(mupi_object_controller.requests, "post", lambda *a, **k: chamadas.append(1))

    resposta = user_client.get(f"/mupi-objects/{ponto.id}/route", params=LONGE)

    assert resposta.status_code == 500
    assert resposta.json()["detail"] == "Chave da API de roteamento não configurada."
    assert chamadas == []


def test_com_chave_ela_vai_no_cabecalho_da_chamada(user_client, ponto, monkeypatch):
    enviados = []

    def post_falso(url, headers, **kwargs):
        enviados.append(headers)
        return RespostaFalsa()

    monkeypatch.setattr(mupi_object_controller, "OPENROUTESERVICE_API_KEY", "chave-do-config")
    monkeypatch.setattr(mupi_object_controller.requests, "post", post_falso)

    resposta = user_client.get(f"/mupi-objects/{ponto.id}/route", params=LONGE)

    assert resposta.status_code == 200
    assert enviados[0]["Authorization"] == "chave-do-config"


def test_chave_so_no_ambiente_nao_e_lida_na_hora_da_requisicao(user_client, ponto, monkeypatch):
    """A chave é lida uma vez, ao iniciar (como as outras), e não a cada chamada."""
    monkeypatch.setattr(mupi_object_controller, "OPENROUTESERVICE_API_KEY", None)
    monkeypatch.setenv("OPENROUTESERVICE_API_KEY", "so-no-ambiente")

    resposta = user_client.get(f"/mupi-objects/{ponto.id}/route", params=LONGE)

    assert resposta.status_code == 500
