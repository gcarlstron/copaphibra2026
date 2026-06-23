"""Tests for the estatísticas (BI links) page."""

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
from app.services.estatisticas import PAINEL_GERAL_URL, painel_do_jogador


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'estat.db'}", connect_args={"check_same_thread": False}
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


def _seed_e_logar(client: TestClient, nome: str, username: str) -> None:
    db = next(client.app.dependency_overrides[get_db]())
    db.add(
        Usuario(
            nome=nome,
            username=username,
            senha_hash=hash_senha("1234"),
            is_admin=(nome == "Administrador"),
            ativo=True,
        )
    )
    db.commit()
    resp = client.post(
        "/login", data={"username": username, "senha": "1234"}, follow_redirects=False
    )
    assert resp.status_code == 303


def test_estatisticas_exige_login(client: TestClient) -> None:
    resp = client.get("/estatisticas", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_jogador_ve_proprio_painel_e_geral(client: TestClient) -> None:
    _seed_e_logar(client, nome="Gustavo", username="gustavo")

    resp = client.get("/estatisticas")
    assert resp.status_code == 200
    assert painel_do_jogador("Gustavo") in resp.text
    assert PAINEL_GERAL_URL in resp.text
    assert "Meu painel" in resp.text
    assert "só o quadro geral" not in resp.text


def test_usuario_sem_painel_ve_so_o_geral(client: TestClient) -> None:
    _seed_e_logar(client, nome="Administrador", username="admin")

    resp = client.get("/estatisticas")
    assert resp.status_code == 200
    assert PAINEL_GERAL_URL in resp.text
    assert "só o quadro geral" in resp.text


def test_painel_do_jogador_lookup() -> None:
    assert painel_do_jogador("Gustavo").startswith("https://")
    assert painel_do_jogador("NãoExiste") is None
