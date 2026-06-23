"""Tests for the admin spreadsheet-import page (/admin/importar).

O import real é mockado — estes testes cobrem a rota (auth, listagem, render do
resultado/erro) e a whitelist do service, sem tocar em banco de verdade.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import create_app
from app.models import Usuario
from app.services.auth import hash_senha
from scripts.importar_planilha import LinhaValidacao, ResultadoImportacao


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'admin_imp.db'}", connect_args={"check_same_thread": False}
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
    return TestClient(app)


def _seed(db: Session, username: str, is_admin: bool) -> None:
    db.add(
        Usuario(
            nome=username.capitalize(),
            username=username,
            senha_hash=hash_senha("1234"),
            is_admin=is_admin,
            ativo=True,
        )
    )
    db.commit()


def _login(client: TestClient, username: str) -> None:
    resp = client.post(
        "/login", data={"username": username, "senha": "1234"}, follow_redirects=False
    )
    assert resp.status_code == 303


def _resultado_fake() -> ResultadoImportacao:
    return ResultadoImportacao(
        arquivo="teste.xlsx",
        usuarios_criados=0,
        usuarios_atualizados=10,
        rodadas_criadas=0,
        rodadas_atualizadas=3,
        jogos_criados=0,
        jogos_atualizados=28,
        jogos_protegidos=44,
        palpites_criados=240,
        palpites_atualizados=40,
        divergencias=[],
        validacao=[LinhaValidacao("Gustavo", 101, 101, True)],
        todos_ok=True,
    )


def test_anonimo_redireciona_para_login(client: TestClient) -> None:
    resp = client.get("/admin/importar", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


def test_nao_admin_recebe_403(client: TestClient, db_session: Session) -> None:
    _seed(db_session, "jogador", is_admin=False)
    _login(client, "jogador")
    assert client.get("/admin/importar", follow_redirects=False).status_code == 403


def test_get_lista_planilhas(client: TestClient, db_session: Session) -> None:
    _seed(db_session, "admin", is_admin=True)
    _login(client, "admin")
    with patch(
        "app.services.importacao.listar_planilhas", return_value=["teste.xlsx"]
    ):
        resp = client.get("/admin/importar")
    assert resp.status_code == 200
    assert "Importar planilha" in resp.text
    assert "teste.xlsx" in resp.text


def test_post_ok_renderiza_resultado(client: TestClient, db_session: Session) -> None:
    _seed(db_session, "admin", is_admin=True)
    _login(client, "admin")
    with patch(
        "app.services.importacao.listar_planilhas", return_value=["teste.xlsx"]
    ), patch(
        "app.services.importacao.importar_planilha", return_value=_resultado_fake()
    ):
        resp = client.post("/admin/importar", data={"arquivo": "teste.xlsx"})
    assert resp.status_code == 200
    assert "240 criados" in resp.text  # palpites
    assert "Gustavo" in resp.text  # linha de validação
    assert "conferem" in resp.text  # todos_ok


def test_post_erro_mostra_banner(client: TestClient, db_session: Session) -> None:
    _seed(db_session, "admin", is_admin=True)
    _login(client, "admin")
    with patch(
        "app.services.importacao.listar_planilhas", return_value=["teste.xlsx"]
    ), patch(
        "app.services.importacao.importar_planilha",
        side_effect=ValueError("planilha inválida"),
    ):
        resp = client.post("/admin/importar", data={"arquivo": "x.xlsx"})
    assert resp.status_code == 400
    assert "planilha inválida" in resp.text


def test_service_whitelist_rejeita_nome_de_fora(client: TestClient) -> None:
    """O service só aceita nomes que estão na pasta (sem path traversal)."""
    from app.services import importacao

    with patch.object(importacao, "listar_planilhas", return_value=["a.xlsx"]):
        with pytest.raises(ValueError):
            importacao.importar_planilha("../../etc/passwd")
        with pytest.raises(ValueError):
            importacao.importar_planilha("b.xlsx")  # não está na pasta
