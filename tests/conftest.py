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
from app.core import admin_auth  # noqa: E402
from app.core.security import csrf_token_for  # noqa: E402
from app.database.database import Base, get_db  # noqa: E402
from app.model.admin import Admin  # noqa: E402
from app.service import auth_user_email_service as codigos  # noqa: E402
from app.service.auth_service import gerar_password_hash  # noqa: E402
from main import app  # noqa: E402

# HTTPS para o cliente de testes aceitar o cookie de sessão "Secure"
BASE_URL = "https://testserver"

ADMIN_EMAIL = "admin@mupi.com"
ADMIN_SENHA = "senha-do-admin"


@pytest.fixture(autouse=True)
def limpar_estado_em_memoria():
    """Cada teste começa sem códigos pendentes nem tentativas de login."""
    codigos.codigos_verificacao.clear()
    codigos.codigos_recuperacao.clear()
    admin_auth._failed_logins.clear()
    yield
    codigos.codigos_verificacao.clear()
    codigos.codigos_recuperacao.clear()
    admin_auth._failed_logins.clear()


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
def app_de_teste(db_session):
    """A aplicação usando o banco de teste."""
    def get_db_teste():
        yield db_session

    app.dependency_overrides[get_db] = get_db_teste
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(app_de_teste, emails_enviados):
    """Cliente sem login."""
    with TestClient(app_de_teste, base_url=BASE_URL) as test_client:
        yield test_client


@pytest.fixture
def admin(db_session):
    admin = Admin(email=ADMIN_EMAIL, password_hash=gerar_password_hash(ADMIN_SENHA))
    db_session.add(admin)
    db_session.commit()
    return admin


def fazer_login(test_client, email=ADMIN_EMAIL, senha=ADMIN_SENHA, **extras):
    return test_client.post(
        "/admin/login",
        data={"email": email, "password": senha, **extras},
        follow_redirects=False,
    )


def csrf_da_sessao(test_client) -> str:
    return csrf_token_for(test_client.cookies.get(admin_auth.SESSION_COOKIE))


@pytest.fixture
def admin_client(app_de_teste, admin, emails_enviados):
    """Cliente com um administrador logado.

    O token CSRF vai no cabeçalho de todas as requisições, então os testes
    das telas do painel não precisam se preocupar com ele.
    """
    with TestClient(app_de_teste, base_url=BASE_URL) as test_client:
        resposta = fazer_login(test_client)
        assert resposta.status_code == 303

        test_client.headers[admin_auth.CSRF_HEADER] = csrf_da_sessao(test_client)
        yield test_client


def passar_intervalo_de_reenvio(email: str) -> None:
    """Simula que o intervalo mínimo entre envios já passou para este e-mail."""
    dados = codigos.codigos_verificacao[email.strip().lower()]
    dados["enviado_em"] -= timedelta(seconds=codigos.RESEND_COOLDOWN_SECONDS + 1)
