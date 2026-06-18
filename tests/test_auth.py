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


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()

    app = create_app()

    def override_get_db() -> Session:
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_hash_senha_verificacao() -> None:
    senha_hash = hash_senha("segredo")

    assert senha_hash != "segredo"
    assert verificar_senha("segredo", senha_hash) is True
    assert verificar_senha("outra-senha", senha_hash) is False


def test_login_logout_flow(client: TestClient) -> None:
    db = next(client.app.dependency_overrides[get_db]())
    usuario = Usuario(
        nome="Thiago",
        username="thiago",
        senha_hash=hash_senha("1234"),
        is_admin=False,
        ativo=True,
    )
    db.add(usuario)
    db.commit()

    response = client.post("/login", data={"username": "thiago", "senha": "1234"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "session=" in response.headers.get("set-cookie", "")

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_rejeita_senha_invalida(client: TestClient) -> None:
    db = next(client.app.dependency_overrides[get_db]())
    usuario = Usuario(
        nome="Ricardo",
        username="ricardo",
        senha_hash=hash_senha("abcd"),
        is_admin=False,
        ativo=True,
    )
    db.add(usuario)
    db.commit()

    response = client.post("/login", data={"username": "ricardo", "senha": "errada"})

    assert response.status_code == 401
