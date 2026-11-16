"""Regra de distância da abertura (VIS-01, VIS-02), posição da visita (VIS-03),
aberturas simultâneas (VIS-05) e configurações do app."""
import pytest
from sqlalchemy.orm import Session

from app.core import config
from app.model.badge import Badge, BadgeRule
from app.model.mupi_object import MupiObject
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit
from app.service import proximity_service

LAT, LNG = -16.6799, -49.2550

# 1 grau de latitude ≈ 111.195 m
METRO_EM_GRAUS = 1 / 111_195


def ao_norte(metros: float) -> dict:
    return {"latitude": LAT + metros * METRO_EM_GRAUS, "longitude": LNG}


@pytest.fixture
def ponto(db_session):
    mupi = MupiObject(name="Teatro", latitude=LAT, longitude=LNG)
    db_session.add(mupi)
    db_session.commit()
    return mupi


def abrir(client, ponto, posicao, accuracy=None):
    corpo = dict(posicao)
    if accuracy is not None:
        corpo["accuracy"] = accuracy
    return client.post(f"/mupi-objects/{ponto.id}/open", json=corpo)


def visitas(db_session):
    db_session.expire_all()
    return db_session.query(UserVisit).all()


# ---------- Configuração (VIS-02) ----------

def test_padroes_do_requisito():
    assert proximity_service.max_distance() == 25
    assert proximity_service.gps_tolerance() == 15


@pytest.mark.parametrize("valor, esperado", [("30", 30.0), ("12,5", 12.5), (" 40 ", 40.0)])
def test_valor_do_env_aceita_virgula(monkeypatch, valor, esperado):
    monkeypatch.setenv("VALOR_DE_TESTE", valor)

    assert config._positive_float("VALOR_DE_TESTE", 25) == esperado


def test_sem_valor_no_env_usa_o_padrao(monkeypatch):
    monkeypatch.delenv("VALOR_DE_TESTE", raising=False)

    assert config._positive_float("VALOR_DE_TESTE", 25) == 25


@pytest.mark.parametrize("valor", ["abc", "0", "-5"])
def test_valor_invalido_no_env_impede_o_servidor_de_subir(monkeypatch, valor):
    monkeypatch.setenv("VALOR_DE_TESTE", valor)

    with pytest.raises(RuntimeError, match="VALOR_DE_TESTE"):
        config._positive_float("VALOR_DE_TESTE", 25)


# ---------- Tolerância ao erro do GPS ----------

@pytest.mark.parametrize("precisao, aceita", [
    (None, 25),     # sem precisão: só a distância máxima
    (0, 25),
    (10, 35),       # GPS bom: soma a precisão
    (15, 40),
    (40, 40),       # GPS ruim: soma no máximo a tolerância
    (5_000, 40),
    (-3, 25),       # valor estranho não reduz o limite
])
def test_distancia_aceita(precisao, aceita):
    assert proximity_service.allowed_distance(precisao) == aceita


def test_distancia_aceita_segue_o_env(monkeypatch):
    monkeypatch.setattr(config, "VISIT_MAX_DISTANCE_M", 50)
    monkeypatch.setattr(config, "VISIT_GPS_TOLERANCE_M", 5)

    assert proximity_service.allowed_distance(10) == 55


# ---------- Abertura (VIS-01) ----------

def test_dentro_da_distancia_maxima_abre_sem_precisao(user_client, ponto):
    assert abrir(user_client, ponto, ao_norte(20)).status_code == 200


def test_um_pouco_fora_sem_precisao_e_recusado(user_client, db_session, ponto):
    resposta = abrir(user_client, ponto, ao_norte(30))

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == (
        "Aproxime-se do MUPI (você está a 30 m; o limite é 25 m)."
    )
    assert visitas(db_session) == []


def test_precisao_do_gps_tolera_o_erro(user_client, ponto):
    """A 30 m com GPS de 10 m de erro: pode estar no local."""
    assert abrir(user_client, ponto, ao_norte(30), accuracy=10).status_code == 200


def test_gps_ruim_nao_libera_o_ponto_de_longe(user_client, ponto):
    """Erro de 200 m soma só 15 m: a 45 m continua longe."""
    resposta = abrir(user_client, ponto, ao_norte(45), accuracy=200)

    assert resposta.status_code == 403
    assert "o limite é 25 m" in resposta.json()["detail"]


def test_gps_ruim_ainda_abre_dentro_do_limite_com_tolerancia(user_client, ponto):
    assert abrir(user_client, ponto, ao_norte(38), accuracy=200).status_code == 200


def test_distancia_maxima_vem_do_env(user_client, ponto, monkeypatch):
    monkeypatch.setattr(config, "VISIT_MAX_DISTANCE_M", 100)

    assert abrir(user_client, ponto, ao_norte(80)).status_code == 200


@pytest.mark.parametrize("precisao", [-1, "muito", 100_001])
def test_precisao_invalida_retorna_422(user_client, ponto, precisao):
    corpo = {**ao_norte(0), "accuracy": precisao}

    resposta = user_client.post(f"/mupi-objects/{ponto.id}/open", json=corpo)

    assert resposta.status_code == 422


def test_precisao_nula_e_aceita(user_client, ponto):
    corpo = {**ao_norte(0), "accuracy": None}

    assert user_client.post(f"/mupi-objects/{ponto.id}/open", json=corpo).status_code == 200


# ---------- Posição da visita (VIS-03) ----------

def test_visita_guarda_a_posicao_e_a_precisao(user_client, db_session, usuario, ponto):
    posicao = ao_norte(12)

    abrir(user_client, ponto, posicao, accuracy=8.5)

    [visita] = visitas(db_session)
    assert visita.user_id == usuario.id
    assert visita.latitude == pytest.approx(posicao["latitude"])
    assert visita.longitude == pytest.approx(posicao["longitude"])
    assert visita.accuracy == 8.5


def test_sem_precisao_a_visita_fica_com_precisao_nula(user_client, db_session, ponto):
    abrir(user_client, ponto, ao_norte(5))

    [visita] = visitas(db_session)
    assert visita.latitude is not None
    assert visita.accuracy is None


def test_abrir_de_novo_mantem_a_posicao_da_primeira_visita(user_client, db_session, ponto):
    abrir(user_client, ponto, ao_norte(5), accuracy=4)
    abrir(user_client, ponto, ao_norte(20), accuracy=12)

    [visita] = visitas(db_session)
    assert visita.accuracy == 4
    assert visita.latitude == pytest.approx(ao_norte(5)["latitude"])


def test_check_in_antigo_tambem_guarda_a_posicao(user_client, db_session, ponto):
    resposta = user_client.post(
        "/users/me/visits",
        json={"object_id": ponto.id, **ao_norte(30), "accuracy": 10},
    )

    assert resposta.status_code == 200
    [visita] = visitas(db_session)
    assert visita.accuracy == 10


# ---------- Aberturas simultâneas (VIS-05) ----------

@pytest.fixture
def corrida(monkeypatch):
    """Simula a abertura que chega junto com outra: ela não enxerga a visita
    que a outra acabou de gravar e tenta gravar de novo."""
    original = Session.get

    def get_sem_ver_a_visita(self, entity, ident, *args, **kwargs):
        if entity is UserVisit:
            return None
        return original(self, entity, ident, *args, **kwargs)

    def ligar():
        monkeypatch.setattr(Session, "get", get_sem_ver_a_visita)

    return ligar


def test_abertura_simultanea_nao_duplica_a_visita(user_client, db_session, ponto, corrida):
    primeira = abrir(user_client, ponto, ao_norte(0))
    corrida()

    segunda = abrir(user_client, ponto, ao_norte(0))

    assert primeira.json()["new_visit"] is True
    assert segunda.status_code == 200
    assert segunda.json()["new_visit"] is False
    assert segunda.json()["awarded"] == []
    assert segunda.json()["visits_total"] == 1
    # O conteúdo é entregue normalmente
    assert segunda.json()["name"] == "Teatro"
    assert len(visitas(db_session)) == 1


def test_abertura_simultanea_nao_duplica_insignias(
    user_client, db_session, usuario, ponto, corrida
):
    contagem = Badge(name="Primeira visita", rule_type=BadgeRule.VISIT_COUNT, required_count=1)
    db_session.add(contagem)
    db_session.commit()

    primeira = abrir(user_client, ponto, ao_norte(0))
    corrida()
    segunda = abrir(user_client, ponto, ao_norte(0))

    assert [b["name"] for b in primeira.json()["awarded"]] == ["Primeira visita"]
    assert segunda.json()["awarded"] == []
    db_session.expire_all()
    assert db_session.query(UserBadge).filter_by(user_id=usuario.id).count() == 1


# ---------- Configurações para o app ----------

def test_configuracoes_do_app_exigem_login(client):
    assert client.get("/app-settings").status_code == 401


def test_app_recebe_a_regra_de_distancia(user_client):
    resposta = user_client.get("/app-settings")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "visit_max_distance_m": 25,
        "visit_gps_tolerance_m": 15,
    }


def test_configuracoes_do_app_seguem_o_env(user_client, monkeypatch):
    monkeypatch.setattr(config, "VISIT_MAX_DISTANCE_M", 40)

    assert user_client.get("/app-settings").json()["visit_max_distance_m"] == 40
