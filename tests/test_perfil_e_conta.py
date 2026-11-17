"""Histórico de visitas (VIS-04), perfil completo (USR-07, INS-08) e
exclusão de conta (USR-08, USR-05)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.controller import user_controller
from app.core.security import create_access_token
from app.model.badge import Badge, BadgeRule
from app.model.email_code import EmailCode
from app.model.mupi_object import MupiObject
from app.model.user import User
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit
from app.service.auth_service import gerar_password_hash

LAT, LNG = -16.6799, -49.2550
SENHA = "Senha-do-teste-123"


def novo_ponto(db_session, nome, **extras):
    ponto = MupiObject(name=nome, latitude=LAT, longitude=LNG, **extras)
    db_session.add(ponto)
    db_session.commit()
    return ponto


def visitar(db_session, usuario, ponto, quando=None):
    visita = UserVisit(user_id=usuario.id, object_id=ponto.id)
    if quando is not None:
        visita.visited_at = quando
    db_session.add(visita)
    db_session.commit()


def abrir(client, ponto):
    return client.post(f"/mupi-objects/{ponto.id}/open", json={"latitude": LAT, "longitude": LNG})


def outro_usuario(db_session, email="outro@exemplo.com"):
    user = User(email=email, password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


AGORA = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


# ---------- Histórico de visitas (VIS-04) ----------

def test_historico_exige_login(client):
    assert client.get("/users/me/visits").status_code == 401


def test_historico_vazio(user_client):
    assert user_client.get("/users/me/visits").json() == []


def test_historico_do_mais_recente_ao_mais_antigo(user_client, db_session, usuario):
    antigo, recente = novo_ponto(db_session, "Antigo"), novo_ponto(db_session, "Recente")
    visitar(db_session, usuario, antigo, AGORA - timedelta(days=3))
    visitar(db_session, usuario, recente, AGORA)

    historico = user_client.get("/users/me/visits").json()

    assert [p["name"] for p in historico] == ["Recente", "Antigo"]
    assert historico[0]["visited_at"].startswith("2026-11-16")
    assert set(historico[0]) == {"id", "name", "photo_url", "visited_at", "available"}


def test_historico_inclui_ponto_desativado_como_indisponivel(user_client, db_session, usuario):
    fechado = novo_ponto(db_session, "Fechado", active=False)
    aberto = novo_ponto(db_session, "Aberto")
    visitar(db_session, usuario, fechado, AGORA - timedelta(days=1))
    visitar(db_session, usuario, aberto, AGORA)

    historico = {p["name"]: p for p in user_client.get("/users/me/visits").json()}

    assert historico["Fechado"]["available"] is False
    assert historico["Aberto"]["available"] is True


def test_historico_traz_a_foto_como_link_temporario(user_client, db_session, usuario):
    ponto = novo_ponto(db_session, "Com foto", photo_key="points/1/photo-x.png")
    visitar(db_session, usuario, ponto)

    [item] = user_client.get("/users/me/visits").json()

    assert "points/1/photo-x.png" in item["photo_url"]
    assert "X-Amz-Signature" in item["photo_url"]


def test_historico_so_tem_as_visitas_do_proprio_usuario(user_client, db_session, usuario):
    meu, dele = novo_ponto(db_session, "Meu"), novo_ponto(db_session, "Dele")
    visitar(db_session, usuario, meu)
    visitar(db_session, outro_usuario(db_session), dele)

    assert [p["name"] for p in user_client.get("/users/me/visits").json()] == ["Meu"]


def test_abrir_o_ponto_entra_no_historico(user_client, db_session):
    ponto = novo_ponto(db_session, "Teatro")

    abrir(user_client, ponto)

    assert [p["id"] for p in user_client.get("/users/me/visits").json()] == [ponto.id]


# ---------- Perfil completo (USR-07, INS-08) ----------

def test_perfil_tem_todos_os_campos(user_client):
    perfil = user_client.get("/users/me").json()

    assert set(perfil) == {
        "id", "email", "created_at", "visits_total", "badges_collected",
        "badges_total", "badges", "in_progress", "locked", "active_route",
        "has_password", "google_linked",
    }
    assert perfil["active_route"] is None


def test_insignia_de_ponto_nao_ganha_aparece_bloqueada_sem_revelar_o_ponto(user_client, db_session):
    teatro = novo_ponto(db_session, "Teatro")
    badge = Badge(name="Visitou o Teatro", description="Segredo", image_key="badges/1/x.png",
                  rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)
    db_session.add(badge)
    db_session.commit()

    perfil = user_client.get("/users/me").json()

    assert perfil["locked"] == [{"id": badge.id, "type": "point_visit"}]
    # Nada que identifique o ponto
    assert "Teatro" not in str(perfil["locked"])
    assert perfil["in_progress"] == []


def test_ao_ganhar_sai_das_bloqueadas(user_client, db_session):
    teatro = novo_ponto(db_session, "Teatro")
    db_session.add(Badge(name="Visitou o Teatro", rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id))
    db_session.commit()

    abrir(user_client, teatro)
    perfil = user_client.get("/users/me").json()

    assert perfil["locked"] == []
    assert [b["name"] for b in perfil["badges"]] == ["Visitou o Teatro"]


def test_bloqueadas_nao_inclui_desativadas_nem_as_de_quantidade(user_client, db_session):
    teatro = novo_ponto(db_session, "Teatro")
    db_session.add_all([
        Badge(name="Desativada", rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id, active=False),
        Badge(name="Cinco pontos", rule_type=BadgeRule.VISIT_COUNT, required_count=5),
    ])
    db_session.commit()

    perfil = user_client.get("/users/me").json()

    assert perfil["locked"] == []
    assert [b["name"] for b in perfil["in_progress"]] == ["Cinco pontos"]
    assert perfil["badges_total"] == 1


# ---------- Exclusão de conta (USR-08) ----------

@pytest.fixture
def com_senha(db_session, usuario):
    usuario.password_hash = gerar_password_hash(SENHA)
    db_session.commit()
    return usuario


def excluir(client, senha=SENHA):
    return client.request("DELETE", "/users/me", json={"password": senha})


def codigo(email, finalidade="recuperacao"):
    agora = datetime.now(timezone.utc)
    return EmailCode(
        email=email, purpose=finalidade, code_hash="0" * 64,
        expires_at=agora + timedelta(minutes=10), sent_at=agora,
    )


def test_exclusao_exige_login(client):
    assert client.request("DELETE", "/users/me", json={"password": SENHA}).status_code == 401


@pytest.mark.parametrize("corpo", [{}, {"password": ""}])
def test_exclusao_exige_a_senha(user_client, com_senha, corpo):
    assert user_client.request("DELETE", "/users/me", json=corpo).status_code == 422


def test_senha_errada_nao_exclui(user_client, db_session, com_senha):
    resposta = excluir(user_client, "senha-errada")

    # 403 e não 401: o app trataria 401 como sessão expirada
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Senha incorreta."
    db_session.expire_all()
    assert db_session.get(User, com_senha.id) is not None


def test_excluir_apaga_o_usuario_e_o_historico_dele(user_client, db_session, com_senha):
    teatro = novo_ponto(db_session, "Teatro")
    badge = Badge(name="Visitou o Teatro", rule_type=BadgeRule.POINT_VISIT, object_id=teatro.id)
    db_session.add(badge)
    db_session.commit()
    abrir(user_client, teatro)
    db_session.add(codigo(com_senha.email))
    db_session.commit()
    user_id = com_senha.id

    resposta = excluir(user_client)

    assert resposta.status_code == 200
    assert resposta.json()["message"] == "Sua conta foi excluída."
    db_session.expire_all()
    assert db_session.get(User, user_id) is None
    assert db_session.query(UserVisit).filter_by(user_id=user_id).count() == 0
    assert db_session.query(UserBadge).filter_by(user_id=user_id).count() == 0
    assert db_session.query(EmailCode).filter_by(email=com_senha.email).count() == 0
    # O ponto e a insígnia continuam
    assert db_session.get(MupiObject, teatro.id) is not None
    assert db_session.get(Badge, badge.id) is not None


def test_depois_de_excluir_o_token_nao_vale_mais(user_client, com_senha):
    excluir(user_client)

    assert user_client.get("/users/me").status_code == 401
    assert user_client.get("/mupi-objects").status_code == 401


def test_excluir_nao_mexe_nos_outros_usuarios(user_client, db_session, com_senha):
    ponto = novo_ponto(db_session, "Teatro")
    outro = outro_usuario(db_session)
    visitar(db_session, outro, ponto)
    db_session.add(codigo(outro.email))
    db_session.commit()

    excluir(user_client)

    db_session.expire_all()
    assert db_session.get(User, outro.id) is not None
    assert db_session.query(UserVisit).filter_by(user_id=outro.id).count() == 1
    assert db_session.query(EmailCode).filter_by(email=outro.email).count() == 1


def test_muitas_senhas_erradas_bloqueiam_por_um_tempo(user_client, db_session, com_senha):
    for _ in range(user_controller.DELETE_ATTEMPTS):
        assert excluir(user_client, "errada").status_code == 403

    # Bloqueado responde 429 mesmo com a senha certa
    resposta = excluir(user_client)

    assert resposta.status_code == 429
    assert "Muitas tentativas" in resposta.json()["detail"]
    db_session.expire_all()
    assert db_session.get(User, com_senha.id) is not None


def test_bloqueio_e_por_conta(client, db_session, com_senha):
    """As tentativas erradas de uma conta não bloqueiam outra."""
    outro = outro_usuario(db_session)
    outro.password_hash = gerar_password_hash(SENHA)
    db_session.commit()

    client.headers["Authorization"] = f"Bearer {create_access_token(com_senha.id, com_senha.token_version)}"
    for _ in range(user_controller.DELETE_ATTEMPTS):
        excluir(client, "errada")

    client.headers["Authorization"] = f"Bearer {create_access_token(outro.id, outro.token_version)}"

    assert excluir(client).status_code == 200
