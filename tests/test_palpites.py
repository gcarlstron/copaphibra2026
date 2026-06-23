from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import create_app
from app.models import Jogo, Palpite, Rodada, Usuario
from app.services.auth import hash_senha


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'palpites.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
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


def _seed_user(db_session: Session) -> Usuario:
    usuario = Usuario(nome="Thiago", username="thiago", senha_hash=hash_senha("1234"), is_admin=False, ativo=True)
    db_session.add(usuario)
    db_session.commit()
    db_session.refresh(usuario)
    return usuario


def _seed_round_and_game(db_session: Session, aberta: bool = True, fechamento_delta: timedelta | None = None) -> Jogo:
    agora = datetime.now(timezone.utc)
    rodada = Rodada(
        nome="1ª Rodada",
        ordem=1,
        aberta=aberta,
        abertura=agora - timedelta(hours=2),
        fechamento=None if fechamento_delta is None else agora + fechamento_delta,
    )
    jogo = Jogo(
        rodada=rodada,
        data_hora=agora + timedelta(hours=1),
        time_casa="Brasil",
        time_visitante="Sérvia",
    )
    db_session.add_all([rodada, jogo])
    db_session.commit()
    db_session.refresh(jogo)
    return jogo


def test_get_palpites_redireciona_sem_login(client: TestClient) -> None:
    response = client.get("/palpites", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_get_palpites_mostra_rodada_e_palpite(client: TestClient, db_session: Session) -> None:
    usuario = _seed_user(db_session)
    jogo = _seed_round_and_game(db_session)
    db_session.add(Palpite(usuario_id=usuario.id, jogo_id=jogo.id, gols_casa=2, gols_visitante=1))
    db_session.commit()

    response = client.post("/login", data={"username": "thiago", "senha": "1234"}, follow_redirects=False)
    assert response.status_code == 303

    response = client.get("/palpites")

    assert response.status_code == 200
    assert "Meus palpites" in response.text
    assert "Brasil" in response.text
    assert "Sérvia" in response.text


def test_post_palpite_cria_e_atualiza(client: TestClient, db_session: Session) -> None:
    usuario = _seed_user(db_session)
    jogo = _seed_round_and_game(db_session)

    response = client.post("/login", data={"username": "thiago", "senha": "1234"}, follow_redirects=False)
    assert response.status_code == 303

    response = client.post("/palpites/%s" % jogo.id, data={"gols_casa": 2, "gols_visitante": 1}, follow_redirects=False)
    assert response.status_code == 303

    palpite = db_session.query(Palpite).filter_by(usuario_id=usuario.id, jogo_id=jogo.id).one()
    assert palpite.gols_casa == 2
    assert palpite.gols_visitante == 1

    response = client.post("/palpites/%s" % jogo.id, data={"gols_casa": 3, "gols_visitante": 1}, follow_redirects=False)
    assert response.status_code == 303

    palpite = db_session.query(Palpite).filter_by(usuario_id=usuario.id, jogo_id=jogo.id).one()
    assert palpite.gols_casa == 3
    assert palpite.gols_visitante == 1


def test_post_palpite_rejeita_rodada_fechada(client: TestClient, db_session: Session) -> None:
    usuario = _seed_user(db_session)
    jogo = _seed_round_and_game(db_session, aberta=True, fechamento_delta=timedelta(minutes=-1))

    response = client.post("/login", data={"username": "thiago", "senha": "1234"}, follow_redirects=False)
    assert response.status_code == 303

    response = client.post("/palpites/%s" % jogo.id, data={"gols_casa": 1, "gols_visitante": 0}, follow_redirects=False)

    assert response.status_code == 409


def test_listar_palpites_rodada_fechada_com_fechamento_naive_nao_levanta_excecao(
    client: TestClient, db_session: Session
) -> None:
    """Bloqueante 1 regression: naive fechamento from SQLite must not cause TypeError.

    When a round is closed (aberta=False) and fechamento is a naive datetime
    (as returned by SQLite), listar_palpites_do_usuario must NOT raise TypeError
    (GET /palpites returns 200). A normalização do naive vive em
    rodada_aberta_para_edicao.
    """
    usuario = _seed_user(db_session)

    # fechamento in the past — naive datetime simulating what SQLite returns
    fechamento_naive = datetime(2026, 6, 1, 12, 0, 0)  # no tzinfo
    rodada = Rodada(
        nome="Rodada Fechada",
        ordem=2,
        aberta=False,
        abertura=datetime(2026, 5, 30, 0, 0, 0),  # naive
        fechamento=fechamento_naive,
    )
    jogo = Jogo(
        rodada=rodada,
        data_hora=datetime(2026, 6, 1, 10, 0, 0),
        time_casa="Brasil",
        time_visitante="Argentina",
    )
    db_session.add_all([rodada, jogo])
    db_session.commit()

    response = client.post("/login", data={"username": "thiago", "senha": "1234"}, follow_redirects=False)
    assert response.status_code == 303

    # Must not crash (was HTTP 500 before the fix)
    response = client.get("/palpites")
    assert response.status_code == 200


def test_post_palpite_rejeita_gols_negativos(client: TestClient, db_session: Session) -> None:
    """Importante 4: backend must reject negative goal values regardless of client-side min=0."""
    _seed_user(db_session)
    jogo = _seed_round_and_game(db_session)

    response = client.post("/login", data={"username": "thiago", "senha": "1234"}, follow_redirects=False)
    assert response.status_code == 303

    response = client.post(
        "/palpites/%s" % jogo.id,
        data={"gols_casa": -1, "gols_visitante": 0},
        follow_redirects=False,
    )
    assert response.status_code in (400, 422)

    # No palpite should have been saved
    from app.models import Palpite as PalpiteModel
    count = db_session.query(PalpiteModel).count()
    assert count == 0
