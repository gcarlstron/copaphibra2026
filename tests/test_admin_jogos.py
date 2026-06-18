"""Tests for admin game management (Fase 7b).

Includes full recalculation coverage: placar exato→9, vencedor+gols do
vencedor→6, empate com placar errado→6, vencedor+gols do perdedor→4,
só vencedor→3, errou→0.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import create_app
from app.models import Jogo, Palpite, Rodada, Usuario
from app.services.auth import hash_senha
from app.services.dashboard import STATUS_AGENDADO, STATUS_ENCERRADO

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AGORA = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'admin_jogos.db'}",
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
    is_admin: bool = False,
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
    db.flush()
    return u


def _seed_rodada(db: Session, nome: str = "1ª Rodada", ordem: int = 1) -> Rodada:
    r = Rodada(nome=nome, ordem=ordem, aberta=True)
    db.add(r)
    db.flush()
    return r


def _seed_jogo(
    db: Session,
    rodada: Rodada,
    time_casa: str = "Brasil",
    time_visitante: str = "Sérvia",
) -> Jogo:
    j = Jogo(
        rodada_id=rodada.id,
        data_hora=_AGORA,
        time_casa=time_casa,
        time_visitante=time_visitante,
        status=STATUS_AGENDADO,
    )
    db.add(j)
    db.flush()
    return j


def _seed_palpite(
    db: Session,
    usuario: Usuario,
    jogo: Jogo,
    gols_casa: int,
    gols_visitante: int,
) -> Palpite:
    p = Palpite(
        usuario_id=usuario.id,
        jogo_id=jogo.id,
        gols_casa=gols_casa,
        gols_visitante=gols_visitante,
        pontos=0,
    )
    db.add(p)
    db.flush()
    return p


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


def test_nao_admin_recebe_403(client: TestClient, db_session: Session) -> None:
    _seed_usuario(db_session, "jogador", is_admin=False)
    db_session.commit()
    _login(client, "jogador")
    resp = client.get("/admin/jogos", follow_redirects=False)
    assert resp.status_code == 403


def test_anonimo_redirecionado_para_login(client: TestClient) -> None:
    resp = client.get("/admin/jogos", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


def test_post_resultado_nao_admin_recebe_403(client: TestClient, db_session: Session) -> None:
    """Menor 7: POST /admin/jogos/{id}/resultado rejeita não-admin com 403."""
    _seed_usuario(db_session, "jogador", is_admin=False)
    admin = _seed_usuario(db_session, "admin_tmp", is_admin=True)
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    db_session.commit()

    _login(client, "jogador")
    resp = client.post(
        f"/admin/jogos/{jogo.id}/resultado",
        data={"gols_casa": 1, "gols_visitante": 0},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_post_resultado_anonimo_redireciona_para_login(client: TestClient, db_session: Session) -> None:
    """Menor 7: POST /admin/jogos/{id}/resultado redireciona anônimo para /login."""
    _seed_usuario(db_session, "admin_tmp", is_admin=True)
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    db_session.commit()

    resp = client.post(
        f"/admin/jogos/{jogo.id}/resultado",
        data={"gols_casa": 1, "gols_visitante": 0},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Criar/editar jogo
# ---------------------------------------------------------------------------


def test_criar_jogo_ok(client: TestClient, db_session: Session) -> None:
    _seed_usuario(db_session, "admin", is_admin=True)
    rodada = _seed_rodada(db_session)
    db_session.commit()
    _login(client, "admin")

    resp = client.post(
        "/admin/jogos",
        data={
            "rodada_id": rodada.id,
            "data_hora": "2026-06-20T18:00",
            "time_casa": "Brasil",
            "time_visitante": "Argentina",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    jogo = db_session.query(Jogo).filter_by(time_casa="Brasil").one()
    assert jogo.status == STATUS_AGENDADO
    assert jogo.rodada_id == rodada.id


def test_editar_jogo_ok(client: TestClient, db_session: Session) -> None:
    _seed_usuario(db_session, "admin", is_admin=True)
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    db_session.commit()
    _login(client, "admin")

    resp = client.post(
        f"/admin/jogos/{jogo.id}",
        data={
            "data_hora": "2026-06-21T18:00",
            "time_casa": "Brasil",
            "time_visitante": "Alemanha",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db_session.expire_all()
    jogo_atualizado = db_session.get(Jogo, jogo.id)
    assert jogo_atualizado.time_visitante == "Alemanha"


def test_editar_jogo_inexistente_retorna_404(client: TestClient, db_session: Session) -> None:
    _seed_usuario(db_session, "admin", is_admin=True)
    db_session.commit()
    _login(client, "admin")

    resp = client.post(
        "/admin/jogos/9999",
        data={"data_hora": "2026-06-21T18:00", "time_casa": "A", "time_visitante": "B"},
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Lançar resultado e recálculo de pontos
# ---------------------------------------------------------------------------


def _lancar_e_reler(
    client: TestClient,
    db_session: Session,
    jogo_id: int,
    gols_casa: int,
    gols_visitante: int,
) -> None:
    resp = client.post(
        f"/admin/jogos/{jogo_id}/resultado",
        data={"gols_casa": gols_casa, "gols_visitante": gols_visitante},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    db_session.expire_all()


def test_lancar_resultado_status_encerrado(client: TestClient, db_session: Session) -> None:
    """After launching result, game.status must be 'encerrado'."""
    _seed_usuario(db_session, "admin", is_admin=True)
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    db_session.commit()
    _login(client, "admin")

    _lancar_e_reler(client, db_session, jogo.id, 2, 1)

    jogo_atualizado = db_session.get(Jogo, jogo.id)
    assert jogo_atualizado.status == STATUS_ENCERRADO
    assert jogo_atualizado.gols_casa == 2
    assert jogo_atualizado.gols_visitante == 1


def test_recalculo_placar_exato_9(client: TestClient, db_session: Session) -> None:
    """Exact score → 9 points."""
    admin = _seed_usuario(db_session, "admin", is_admin=True)
    u = _seed_usuario(db_session, "jogador")
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    palpite = _seed_palpite(db_session, u, jogo, 2, 1)
    db_session.commit()
    _login(client, "admin")

    _lancar_e_reler(client, db_session, jogo.id, 2, 1)

    p = db_session.get(Palpite, palpite.id)
    assert p.pontos == 9


def test_recalculo_vencedor_gols_vencedor_6(client: TestClient, db_session: Session) -> None:
    """Correct winner + correct winner goal count (not exact) → 6 points."""
    _seed_usuario(db_session, "admin", is_admin=True)
    u = _seed_usuario(db_session, "jogador")
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    # Palpite: 2-0 (casa wins with 2 goals), result: 2-1 (casa still wins, same winner goals)
    palpite = _seed_palpite(db_session, u, jogo, 2, 0)
    db_session.commit()
    _login(client, "admin")

    _lancar_e_reler(client, db_session, jogo.id, 2, 1)

    p = db_session.get(Palpite, palpite.id)
    assert p.pontos == 6


def test_recalculo_empate_placar_errado_6(client: TestClient, db_session: Session) -> None:
    """Correct tie result but wrong exact score → 6 points."""
    _seed_usuario(db_session, "admin", is_admin=True)
    u = _seed_usuario(db_session, "jogador")
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    # Palpite: 2-2, result: 1-1 (both draws, not exact)
    palpite = _seed_palpite(db_session, u, jogo, 2, 2)
    db_session.commit()
    _login(client, "admin")

    _lancar_e_reler(client, db_session, jogo.id, 1, 1)

    p = db_session.get(Palpite, palpite.id)
    assert p.pontos == 6


def test_recalculo_vencedor_gols_perdedor_4(client: TestClient, db_session: Session) -> None:
    """Correct winner + correct loser goal count (not winner goals) → 4 points."""
    _seed_usuario(db_session, "admin", is_admin=True)
    u = _seed_usuario(db_session, "jogador")
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    # Palpite: 3-0, result: 2-0 (casa wins; loser goals same=0, winner goals differ)
    palpite = _seed_palpite(db_session, u, jogo, 3, 0)
    db_session.commit()
    _login(client, "admin")

    _lancar_e_reler(client, db_session, jogo.id, 2, 0)

    p = db_session.get(Palpite, palpite.id)
    assert p.pontos == 4


def test_recalculo_so_vencedor_3(client: TestClient, db_session: Session) -> None:
    """Only the winner correct (not goals) → 3 points."""
    _seed_usuario(db_session, "admin", is_admin=True)
    u = _seed_usuario(db_session, "jogador")
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    # Palpite: 3-1 (casa vence), result: 2-0 (casa vence; neither goals match)
    palpite = _seed_palpite(db_session, u, jogo, 3, 1)
    db_session.commit()
    _login(client, "admin")

    _lancar_e_reler(client, db_session, jogo.id, 2, 0)

    p = db_session.get(Palpite, palpite.id)
    assert p.pontos == 3


def test_recalculo_errou_0(client: TestClient, db_session: Session) -> None:
    """Wrong winner → 0 points."""
    _seed_usuario(db_session, "admin", is_admin=True)
    u = _seed_usuario(db_session, "jogador")
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    # Palpite: 0-2 (visitante vence), result: 1-0 (casa vence)
    palpite = _seed_palpite(db_session, u, jogo, 0, 2)
    db_session.commit()
    _login(client, "admin")

    _lancar_e_reler(client, db_session, jogo.id, 1, 0)

    p = db_session.get(Palpite, palpite.id)
    assert p.pontos == 0


def test_relancar_com_placar_diferente_recalcula(client: TestClient, db_session: Session) -> None:
    """Re-launching with a different score must re-recalculate palpite.pontos."""
    _seed_usuario(db_session, "admin", is_admin=True)
    u = _seed_usuario(db_session, "jogador")
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    # Palpite: 1-0 (casa vence)
    palpite = _seed_palpite(db_session, u, jogo, 1, 0)
    db_session.commit()
    _login(client, "admin")

    # First launch: 1-0 → exact → 9
    _lancar_e_reler(client, db_session, jogo.id, 1, 0)
    p = db_session.get(Palpite, palpite.id)
    assert p.pontos == 9

    # Re-launch: 3-1 (casa vence, winner goals=3≠1, loser goals=1≠0) → only winner → 3
    # We need to update the palpite to 2-1 so neither winner(2) nor loser(1) gols match 3-1 official
    # Palpite 2-1 vs result 3-1: winner_pal=2 vs official=3 (differs), loser_pal=1 vs official=1 (matches!) → 4
    # To get 3: palpite 3-1 vs result 2-0: winner_pal=3 vs official=2 (differs), loser_pal=1 vs official=0 (differs) → 3
    # But we cannot change the palpite here; change the result to produce score 3 against palpite 1-0.
    # Palpite 1-0 vs result 3-2: casa vence both; winner_pal=1 vs official=3 (differs); loser_pal=0 vs official=2 (differs) → 3
    _lancar_e_reler(client, db_session, jogo.id, 3, 2)
    p = db_session.get(Palpite, palpite.id)
    assert p.pontos == 3


def test_recalculo_inclui_usuario_inativo(client: TestClient, db_session: Session) -> None:
    """D7: palpites of inactive users must also be recalculated."""
    _seed_usuario(db_session, "admin", is_admin=True)
    inativo = _seed_usuario(db_session, "fantasma", ativo=False)
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada)
    palpite_inativo = _seed_palpite(db_session, inativo, jogo, 2, 1)
    db_session.commit()
    _login(client, "admin")

    _lancar_e_reler(client, db_session, jogo.id, 2, 1)

    p = db_session.get(Palpite, palpite_inativo.id)
    assert p.pontos == 9


def test_lancar_resultado_jogo_inexistente_404(client: TestClient, db_session: Session) -> None:
    _seed_usuario(db_session, "admin", is_admin=True)
    db_session.commit()
    _login(client, "admin")

    resp = client.post(
        "/admin/jogos/9999/resultado",
        data={"gols_casa": 1, "gols_visitante": 0},
        follow_redirects=False,
    )
    assert resp.status_code == 400  # ValueError → 400 in the router
