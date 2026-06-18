"""Tests for admin user management (Fase 7c)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import create_app
from app.models import Usuario
from app.services.auth import hash_senha, verificar_senha

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'admin_usuarios.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_usuario(
    db: Session,
    username: str,
    senha: str = "1234",
    is_admin: bool = False,
    ativo: bool = True,
) -> Usuario:
    u = Usuario(
        nome=username.capitalize(),
        username=username,
        senha_hash=hash_senha(senha),
        is_admin=is_admin,
        ativo=ativo,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _login(client: TestClient, username: str, senha: str = "1234") -> None:
    resp = client.post(
        "/login",
        data={"username": username, "senha": senha},
        follow_redirects=False,
    )
    assert resp.status_code == 303


def _logout(client: TestClient) -> None:
    client.post("/logout", follow_redirects=False)


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_nao_admin_recebe_403(client: TestClient, db_session: Session) -> None:
    _seed_usuario(db_session, "jogador", is_admin=False)
    _login(client, "jogador")
    resp = client.get("/admin/usuarios", follow_redirects=False)
    assert resp.status_code == 403


def test_anonimo_redirecionado_para_login(client: TestClient) -> None:
    resp = client.get("/admin/usuarios", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


def test_post_ativo_nao_admin_recebe_403(client: TestClient, db_session: Session) -> None:
    """Menor 7: POST /admin/usuarios/{id}/ativo rejeita não-admin com 403."""
    alvo = _seed_usuario(db_session, "alvo")
    _seed_usuario(db_session, "jogador", is_admin=False)
    _login(client, "jogador")

    resp = client.post(
        f"/admin/usuarios/{alvo.id}/ativo",
        data={"ativo": "false"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_post_ativo_anonimo_redireciona_para_login(client: TestClient, db_session: Session) -> None:
    """Menor 7: POST /admin/usuarios/{id}/ativo redireciona anônimo para /login."""
    alvo = _seed_usuario(db_session, "alvo")

    resp = client.post(
        f"/admin/usuarios/{alvo.id}/ativo",
        data={"ativo": "false"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Criar usuário
# ---------------------------------------------------------------------------


def test_criar_usuario_hash_e_verificacao(client: TestClient, db_session: Session) -> None:
    """Password must be stored hashed (hash != plain) and verification must pass."""
    _seed_usuario(db_session, "admin", is_admin=True)
    _login(client, "admin")

    resp = client.post(
        "/admin/usuarios",
        data={"nome": "Novo Jogador", "username": "novo", "senha": "segredo123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    usuario = db_session.query(Usuario).filter_by(username="novo").one()
    assert usuario.senha_hash != "segredo123"  # stored hashed
    assert verificar_senha("segredo123", usuario.senha_hash)  # verification works


def test_criar_usuario_username_duplicado_falha(client: TestClient, db_session: Session) -> None:
    """Duplicate username must return 400."""
    _seed_usuario(db_session, "admin", is_admin=True)
    _seed_usuario(db_session, "existente")
    _login(client, "admin")

    resp = client.post(
        "/admin/usuarios",
        data={"nome": "Outro", "username": "existente", "senha": "abc"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Resetar senha
# ---------------------------------------------------------------------------


def test_resetar_senha_login_com_nova_senha(client: TestClient, db_session: Session) -> None:
    """After password reset, the user can login with the new password."""
    _seed_usuario(db_session, "admin", is_admin=True)
    alvo = _seed_usuario(db_session, "alvo", senha="velha")
    _login(client, "admin")

    resp = client.post(
        f"/admin/usuarios/{alvo.id}/senha",
        data={"nova_senha": "nova123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    # Logout and login with new password.
    _logout(client)
    resp2 = client.post(
        "/login",
        data={"username": "alvo", "senha": "nova123"},
        follow_redirects=False,
    )
    assert resp2.status_code == 303  # login succeeded

    # Old password no longer works.
    _logout(client)
    resp3 = client.post(
        "/login",
        data={"username": "alvo", "senha": "velha"},
        follow_redirects=False,
    )
    assert resp3.status_code == 401


def test_resetar_senha_usuario_inexistente_404(client: TestClient, db_session: Session) -> None:
    _seed_usuario(db_session, "admin", is_admin=True)
    _login(client, "admin")

    resp = client.post(
        "/admin/usuarios/9999/senha",
        data={"nova_senha": "qualquer"},
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Desativar usuário
# ---------------------------------------------------------------------------


def test_desativar_usuario_login_falha(client: TestClient, db_session: Session) -> None:
    """Deactivated user cannot login."""
    _seed_usuario(db_session, "admin", is_admin=True)
    alvo = _seed_usuario(db_session, "alvo")
    _login(client, "admin")

    resp = client.post(
        f"/admin/usuarios/{alvo.id}/ativo",
        data={"ativo": "false"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    _logout(client)
    resp2 = client.post(
        "/login",
        data={"username": "alvo", "senha": "1234"},
        follow_redirects=False,
    )
    assert resp2.status_code == 401


def test_ativar_usuario_login_funciona(client: TestClient, db_session: Session) -> None:
    """Re-activating a user allows login again."""
    _seed_usuario(db_session, "admin", is_admin=True)
    alvo = _seed_usuario(db_session, "alvo", ativo=False)
    _login(client, "admin")

    resp = client.post(
        f"/admin/usuarios/{alvo.id}/ativo",
        data={"ativo": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    _logout(client)
    resp2 = client.post(
        "/login",
        data={"username": "alvo", "senha": "1234"},
        follow_redirects=False,
    )
    assert resp2.status_code == 303  # success


def test_definir_ativo_usuario_inexistente_404(client: TestClient, db_session: Session) -> None:
    _seed_usuario(db_session, "admin", is_admin=True)
    _login(client, "admin")

    resp = client.post(
        "/admin/usuarios/9999/ativo",
        data={"ativo": "false"},
        follow_redirects=False,
    )
    assert resp.status_code == 404
