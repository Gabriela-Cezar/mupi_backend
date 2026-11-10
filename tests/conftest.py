import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["RESEND_API_KEY"] = "re_teste"
os.environ["EMAIL_FROM"] = "MUPI Testes <teste@exemplo.com>"
os.environ["SECRET_KEY"] = "chave-secreta-apenas-para-testes"

from datetime import timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.controller import auth_controller  # noqa: E402
from app.database.database import Base, get_db  # noqa: E402
from app.service import auth_user_email_service as codigos  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def limpar_codigos():
    """Cada teste começa sem nenhum código pendente na memória."""
    codigos.codigos_verificacao.clear()
    codigos.codigos_recuperacao.clear()
    yield
    codigos.codigos_verificacao.clear()
    codigos.codigos_recuperacao.clear()


@pytest.fixture
def db_session():
    """Banco SQLite em memória, recriado a cada teste."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # O main já importou todos os models, então todas as tabelas são criadas
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def emails_enviados(monkeypatch):
    """Substitui o envio real de e-mail e guarda o que seria enviado."""
    enviados = []

    def send_email_falso(recipient, subject, html_content):
        enviados.append({
            "recipient": recipient,
            "subject": subject,
            "html_content": html_content,
        })
        return True

    monkeypatch.setattr(auth_controller, "send_email", send_email_falso)
    return enviados


@pytest.fixture
def client(db_session, emails_enviados):
    def get_db_teste():
        yield db_session

    app.dependency_overrides[get_db] = get_db_teste
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def passar_intervalo_de_reenvio(email: str) -> None:
    """Simula que o intervalo mínimo entre envios já passou para este e-mail."""
    dados = codigos.codigos_verificacao[email.strip().lower()]
    dados["enviado_em"] -= timedelta(seconds=codigos.RESEND_COOLDOWN_SECONDS + 1)
