"""Tests for admin round management (Fase 7a).

Follows the fixture/helper pattern established in tests/test_jogos.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import create_app
from app.models import Rodada, Usuario
from app.services.auth import hash_senha

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'admin_rodadas.db'}",
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
    username: str = "admin",
    is_admin: bool = True,
    ativo: bool = True,
) -> Usuario:
    u = Usuario(
        nome=username.capitalize(),
        username=username,
        senha_hash=hash_senha("1234"),
        is_admin=is_admin,
        ativo=ativo,
    )
    db.add(u)
    db.commit()
    return u


def _seed_rodada(db: Session, nome: str = "1ª Rodada", ordem: int = 1) -> Rodada:
    r = Rodada(nome=nome, ordem=ordem, aberta=False)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _login(client: TestClient, username: str, senha: str = "1234") -> None:
    resp = client.post(
        "/login",
        data={"username": username, "senha": senha},
        follow_redirects=False,
    )
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_nao_admin_logado_recebe_403(client: TestClient, db_session: Session) -> None:
    """Logged-in non-admin user → 403."""
    _seed_usuario(db_session, username="jogador", is_admin=False)
    _login(client, "jogador")
    resp = client.get("/admin/rodadas", follow_redirects=False)
    assert resp.status_code == 403


def test_anonimo_redirecionado_para_login(client: TestClient) -> None:
    """Anonymous request → 303 redirect to /login."""
    resp = client.get("/admin/rodadas", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Criar rodada
# ---------------------------------------------------------------------------


def test_criar_rodada_ok(client: TestClient, db_session: Session) -> None:
    """Admin can create a round; it appears in the DB."""
    _seed_usuario(db_session)
    _login(client, "admin")

    resp = client.post(
        "/admin/rodadas",
        data={"nome": "1ª Rodada", "ordem": 1},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    rodada = db_session.query(Rodada).filter_by(nome="1ª Rodada").one()
    assert rodada.ordem == 1


def test_criar_rodada_ordem_duplicada_falha(client: TestClient, db_session: Session) -> None:
    """Creating a second round with the same ordem must fail (400)."""
    _seed_usuario(db_session)
    _seed_rodada(db_session, nome="1ª Rodada", ordem=1)
    _login(client, "admin")

    resp = client.post(
        "/admin/rodadas",
        data={"nome": "Outra", "ordem": 1},
        follow_redirects=False,
    )
    # Service raises ValueError → router returns 400.
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Atualizar rodada
# ---------------------------------------------------------------------------


def test_abrir_fechar_rodada_altera_flag(client: TestClient, db_session: Session) -> None:
    """POST /admin/rodadas/{id} with aberta=true sets the flag."""
    _seed_usuario(db_session)
    rodada = _seed_rodada(db_session)
    assert rodada.aberta is False
    _login(client, "admin")

    resp = client.post(
        f"/admin/rodadas/{rodada.id}",
        data={"aberta": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db_session.expire_all()
    rodada_atualizada = db_session.get(Rodada, rodada.id)
    assert rodada_atualizada.aberta is True

    # Now close it.
    resp2 = client.post(
        f"/admin/rodadas/{rodada.id}",
        data={"aberta": "false"},
        follow_redirects=False,
    )
    assert resp2.status_code == 303
    db_session.expire_all()
    rodada_fechada = db_session.get(Rodada, rodada.id)
    assert rodada_fechada.aberta is False


def test_definir_janela_persiste(client: TestClient, db_session: Session) -> None:
    """Setting abertura and fechamento persists them."""
    _seed_usuario(db_session)
    rodada = _seed_rodada(db_session)
    _login(client, "admin")

    abertura_str = "2026-06-20T10:00"
    fechamento_str = "2026-06-25T10:00"

    resp = client.post(
        f"/admin/rodadas/{rodada.id}",
        data={"aberta": "true", "abertura": abertura_str, "fechamento": fechamento_str},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db_session.expire_all()
    rodada_atualizada = db_session.get(Rodada, rodada.id)
    assert rodada_atualizada.abertura is not None
    assert rodada_atualizada.fechamento is not None


def test_abertura_maior_que_fechamento_rejeitado(client: TestClient, db_session: Session) -> None:
    """abertura > fechamento must be rejected with 400."""
    _seed_usuario(db_session)
    rodada = _seed_rodada(db_session)
    _login(client, "admin")

    resp = client.post(
        f"/admin/rodadas/{rodada.id}",
        data={
            "aberta": "true",
            "abertura": "2026-06-25T10:00",
            "fechamento": "2026-06-20T10:00",  # earlier than abertura
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_editar_rodada_inexistente_retorna_404(client: TestClient, db_session: Session) -> None:
    """Editing a non-existent round id → 404."""
    _seed_usuario(db_session)
    _login(client, "admin")

    resp = client.post(
        "/admin/rodadas/9999",
        data={"aberta": "false"},
        follow_redirects=False,
    )
    assert resp.status_code == 404
