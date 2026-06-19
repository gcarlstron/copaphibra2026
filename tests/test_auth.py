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


def _criar_e_logar(client: TestClient, senha: str = "senha-antiga") -> Usuario:
    db = next(client.app.dependency_overrides[get_db]())
    usuario = Usuario(
        nome="Gustavo",
        username="gustavo",
        senha_hash=hash_senha(senha),
        is_admin=False,
        ativo=True,
    )
    db.add(usuario)
    db.commit()
    resposta = client.post("/login", data={"username": "gustavo", "senha": senha})
    assert resposta.status_code in (200, 303)
    return usuario


def test_trocar_senha_sucesso(client: TestClient) -> None:
    usuario = _criar_e_logar(client, senha="senha-antiga")

    response = client.post(
        "/trocar-senha",
        data={
            "senha_atual": "senha-antiga",
            "nova_senha": "senha-nova-123",
            "confirmacao": "senha-nova-123",
        },
    )

    assert response.status_code == 200
    assert "Senha alterada com sucesso" in response.text

    db = next(client.app.dependency_overrides[get_db]())
    db.refresh(usuario)
    assert verificar_senha("senha-nova-123", usuario.senha_hash) is True
    assert verificar_senha("senha-antiga", usuario.senha_hash) is False


def test_trocar_senha_atual_incorreta(client: TestClient) -> None:
    usuario = _criar_e_logar(client, senha="senha-antiga")

    response = client.post(
        "/trocar-senha",
        data={
            "senha_atual": "errada",
            "nova_senha": "senha-nova-123",
            "confirmacao": "senha-nova-123",
        },
    )

    assert response.status_code == 400
    assert "Senha atual incorreta" in response.text

    db = next(client.app.dependency_overrides[get_db]())
    db.refresh(usuario)
    assert verificar_senha("senha-antiga", usuario.senha_hash) is True


def test_trocar_senha_confirmacao_diferente(client: TestClient) -> None:
    _criar_e_logar(client, senha="senha-antiga")

    response = client.post(
        "/trocar-senha",
        data={
            "senha_atual": "senha-antiga",
            "nova_senha": "senha-nova-123",
            "confirmacao": "outra-coisa-456",
        },
    )

    assert response.status_code == 400
    assert "confirmação" in response.text.lower()


def test_trocar_senha_curta_rejeitada(client: TestClient) -> None:
    _criar_e_logar(client, senha="senha-antiga")

    response = client.post(
        "/trocar-senha",
        data={"senha_atual": "senha-antiga", "nova_senha": "ab1", "confirmacao": "ab1"},
    )

    assert response.status_code == 400
    assert "pelo menos" in response.text.lower()


def test_trocar_senha_igual_atual_rejeitada(client: TestClient) -> None:
    _criar_e_logar(client, senha="senha-antiga")

    response = client.post(
        "/trocar-senha",
        data={
            "senha_atual": "senha-antiga",
            "nova_senha": "senha-antiga",
            "confirmacao": "senha-antiga",
        },
    )

    assert response.status_code == 400
    assert "diferente da atual" in response.text.lower()


def test_trocar_senha_exige_login(client: TestClient) -> None:
    get_resp = client.get("/trocar-senha", follow_redirects=False)
    assert get_resp.status_code == 303
    assert get_resp.headers["location"] == "/login"

    post_resp = client.post(
        "/trocar-senha",
        data={"senha_atual": "x", "nova_senha": "yyyyyy", "confirmacao": "yyyyyy"},
        follow_redirects=False,
    )
    assert post_resp.status_code == 303
    assert post_resp.headers["location"] == "/login"
