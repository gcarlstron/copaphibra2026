"""Tests for the regras (scoring rules) page."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import create_app
from app.models import Usuario
from app.services.auth import hash_senha


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'regras.db'}", connect_args={"check_same_thread": False}
    )
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


def test_regras_exige_login(client: TestClient) -> None:
    resp = client.get("/regras", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_regras_mostra_legenda(client: TestClient) -> None:
    db = next(client.app.dependency_overrides[get_db]())
    db.add(
        Usuario(
            nome="Thiago",
            username="thiago",
            senha_hash=hash_senha("1234"),
            is_admin=False,
            ativo=True,
        )
    )
    db.commit()
    resp = client.post(
        "/login", data={"username": "thiago", "senha": "1234"}, follow_redirects=False
    )
    assert resp.status_code == 303

    resp = client.get("/regras")
    assert resp.status_code == 200
    assert "Regras de pontuação" in resp.text
    assert "placar exato" in resp.text
    assert "só o vencedor" in resp.text
    assert "Critério de desempate" in resp.text
    assert "Errou o vencedor" in resp.text
