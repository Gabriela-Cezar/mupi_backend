"""Exclusões não apagam o histórico dos usuários (FAL-11).

O banco recusa excluir um ponto que alguém visitou ou uma insígnia que
alguém conquistou. Os testes rodam num SQLite com as chaves estrangeiras
ligadas (por padrão o SQLite as ignora), criado de dois jeitos: pelos
models e pelas migrações do Alembic.
"""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.all_models import Base
from app.model.badge import Badge, BadgeRule
from app.model.midia import MediaType, MupiObjectMedia
from app.model.mupi_object import MupiObject
from app.model.mupi_object_badge import MupiObjectBadge
from app.model.user import User
from app.model.user_badge import UserBadge
from app.model.user_visit import UserVisit

RAIZ = Path(__file__).resolve().parent.parent


def ligar_chaves_estrangeiras(engine):
    @event.listens_for(engine, "connect")
    def _pragma(conexao, _):
        conexao.execute("PRAGMA foreign_keys=ON")

    return engine


def alembic_cfg(url):
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(params=["models", "migracoes"])
def db(request, tmp_path):
    url = f"sqlite:///{tmp_path / 'fal11.db'}"

    if request.param == "models":
        Base.metadata.create_all(create_engine(url))
    else:
        command.upgrade(alembic_cfg(url), "head")

    engine = ligar_chaves_estrangeiras(create_engine(url))
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def usuario(db):
    user = User(email="visitante@exemplo.com", password_hash="x")
    db.add(user)
    db.commit()
    return user


def criar_ponto(db, nome="Ponto"):
    ponto = MupiObject(name=nome, latitude=-16.68, longitude=-49.25)
    db.add(ponto)
    db.commit()
    return ponto


def criar_insignia(db, nome="Insígnia"):
    insignia = Badge(name=nome, rule_type=BadgeRule.MANUAL)
    db.add(insignia)
    db.commit()
    return insignia


def excluir(db, item):
    db.delete(item)
    db.commit()


def contar(db, modelo):
    return len(db.scalars(select(modelo)).all())


# ---------- Pontos ----------

def test_excluir_ponto_visitado_e_recusado(db, usuario):
    ponto = criar_ponto(db)
    db.add(UserVisit(user_id=usuario.id, object_id=ponto.id))
    db.commit()

    with pytest.raises(IntegrityError):
        excluir(db, ponto)
    db.rollback()

    assert db.get(MupiObject, ponto.id) is not None
    assert db.get(UserVisit, (usuario.id, ponto.id)) is not None


def test_ponto_visitado_pode_ser_desativado(db, usuario):
    ponto = criar_ponto(db)
    db.add(UserVisit(user_id=usuario.id, object_id=ponto.id))
    db.commit()

    ponto.active = False
    db.commit()

    assert db.get(UserVisit, (usuario.id, ponto.id)) is not None


def test_excluir_ponto_sem_visitas_funciona(db):
    ponto = criar_ponto(db)
    insignia = criar_insignia(db)
    db.add(MupiObjectMedia(object_id=ponto.id, type=MediaType.IMAGE, data=b"x", mime_type="image/png"))
    db.add(MupiObjectBadge(object_id=ponto.id, badge_id=insignia.id))
    db.commit()

    excluir(db, ponto)

    assert db.get(MupiObject, ponto.id) is None
    assert contar(db, MupiObjectMedia) == 0      # fotos e vídeos do ponto vão junto
    assert contar(db, MupiObjectBadge) == 0      # só a ligação; a insígnia fica
    assert db.get(Badge, insignia.id) is not None


# ---------- Insígnias ----------

def test_excluir_insignia_conquistada_e_recusado(db, usuario):
    insignia = criar_insignia(db)
    db.add(UserBadge(user_id=usuario.id, badge_id=insignia.id))
    db.commit()

    with pytest.raises(IntegrityError):
        excluir(db, insignia)
    db.rollback()

    assert db.get(Badge, insignia.id) is not None
    assert db.get(UserBadge, (usuario.id, insignia.id)) is not None


def test_excluir_insignia_nao_conquistada_funciona(db):
    insignia = criar_insignia(db)
    ponto = criar_ponto(db)
    db.add(MupiObjectBadge(object_id=ponto.id, badge_id=insignia.id))
    db.commit()

    excluir(db, insignia)

    assert db.get(Badge, insignia.id) is None
    assert contar(db, MupiObjectBadge) == 0
    assert db.get(MupiObject, ponto.id) is not None


# ---------- Usuários ----------

def test_excluir_usuario_apaga_o_historico_dele(db, usuario):
    """A conta excluída leva junto as próprias visitas e conquistas."""
    ponto = criar_ponto(db)
    insignia = criar_insignia(db)
    db.add(UserVisit(user_id=usuario.id, object_id=ponto.id))
    db.add(UserBadge(user_id=usuario.id, badge_id=insignia.id, collected_at_object_id=ponto.id))
    db.commit()

    excluir(db, usuario)

    assert contar(db, UserVisit) == 0
    assert contar(db, UserBadge) == 0
    assert db.get(MupiObject, ponto.id) is not None
    assert db.get(Badge, insignia.id) is not None


def test_excluir_usuario_nao_afeta_o_historico_dos_outros(db, usuario):
    outro = User(email="outro@exemplo.com", password_hash="x")
    ponto = criar_ponto(db)
    db.add(outro)
    db.commit()
    db.add_all([
        UserVisit(user_id=usuario.id, object_id=ponto.id),
        UserVisit(user_id=outro.id, object_id=ponto.id),
    ])
    db.commit()

    excluir(db, usuario)

    assert db.get(UserVisit, (outro.id, ponto.id)) is not None


# ---------- Migração 0003 ----------

def test_desfazer_a_0003_volta_a_apagar_em_cascata(tmp_path):
    """Confere que o downgrade restaura o comportamento antigo."""
    url = f"sqlite:///{tmp_path / 'downgrade.db'}"
    cfg = alembic_cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002")

    engine = ligar_chaves_estrangeiras(create_engine(url))
    with Session(engine) as db:
        usuario = User(email="v@exemplo.com", password_hash="x")
        ponto = criar_ponto(db)
        db.add(usuario)
        db.commit()
        db.add(UserVisit(user_id=usuario.id, object_id=ponto.id))
        db.commit()

        excluir(db, ponto)

        assert contar(db, UserVisit) == 0
    engine.dispose()
