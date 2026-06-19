"""Tests for listar_todos_os_jogos (Fase 11c).

Cobre:
- meus_pontos correto por jogo (palpite encerrado com pontos); jogo sem palpite → None
- agrupamento por Rodada.ordem e jogos por data_hora
- escudo ausente (time sem alias ou escudo_url None) → campo None, sem erro
- escudo presente vem correto
- GET /jogos exige login (anônimo → redirect /login)
- lista NÃO traz pontos/palpites de terceiros (mesmo com rodada aberta)
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
from app.models import Jogo, Palpite, Rodada, Usuario
from app.models.team_alias import TeamAlias
from app.services.auth import hash_senha
from app.services.dashboard import STATUS_AGENDADO, STATUS_ENCERRADO
from app.services.jogos import listar_todos_os_jogos

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AGORA = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'lista_jogos.db'}",
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
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_usuario(
    db: Session,
    nome: str,
    username: str,
    ativo: bool = True,
    is_admin: bool = False,
) -> Usuario:
    u = Usuario(
        nome=nome,
        username=username,
        senha_hash=hash_senha("1234"),
        is_admin=is_admin,
        ativo=ativo,
    )
    db.add(u)
    db.flush()
    return u


def _seed_rodada(
    db: Session,
    nome: str = "1ª Rodada",
    ordem: int = 1,
    aberta: bool = False,
    abertura: datetime | None = None,
    fechamento: datetime | None = None,
) -> Rodada:
    r = Rodada(nome=nome, ordem=ordem, aberta=aberta, abertura=abertura, fechamento=fechamento)
    db.add(r)
    db.flush()
    return r


def _seed_jogo(
    db: Session,
    rodada: Rodada,
    time_casa: str = "Brasil",
    time_visitante: str = "Sérvia",
    data_hora: datetime | None = None,
    status: str = STATUS_AGENDADO,
    gols_casa: int | None = None,
    gols_visitante: int | None = None,
) -> Jogo:
    j = Jogo(
        rodada_id=rodada.id,
        data_hora=data_hora or _AGORA + timedelta(hours=1),
        time_casa=time_casa,
        time_visitante=time_visitante,
        status=status,
        gols_casa=gols_casa,
        gols_visitante=gols_visitante,
    )
    db.add(j)
    db.flush()
    return j


def _seed_palpite(
    db: Session,
    usuario: Usuario,
    jogo: Jogo,
    gols_casa: int = 1,
    gols_visitante: int = 0,
    pontos: int = 0,
) -> Palpite:
    p = Palpite(
        usuario_id=usuario.id,
        jogo_id=jogo.id,
        gols_casa=gols_casa,
        gols_visitante=gols_visitante,
        pontos=pontos,
    )
    db.add(p)
    db.flush()
    return p


def _seed_alias(
    db: Session,
    abrev: str,
    nome: str,
    escudo_url: str | None = None,
) -> TeamAlias:
    ta = TeamAlias(abreviacao=abrev, nome=nome, nome_en=nome, escudo_url=escudo_url)
    db.add(ta)
    db.flush()
    return ta


def _login(client: TestClient, username: str, senha: str = "1234") -> None:
    resp = client.post("/login", data={"username": username, "senha": senha}, follow_redirects=False)
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Testes: meus_pontos
# ---------------------------------------------------------------------------


def test_meus_pontos_correto_para_jogo_com_palpite(db_session: Session) -> None:
    """meus_pontos devolve o valor de Palpite.pontos do próprio usuário."""
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(
        db_session, rodada, status=STATUS_ENCERRADO, gols_casa=2, gols_visitante=1
    )
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    _seed_palpite(db_session, usuario, jogo, gols_casa=2, gols_visitante=1, pontos=9)
    db_session.commit()

    dados = listar_todos_os_jogos(db_session, usuario)

    assert len(dados.grupos) == 1
    item = dados.grupos[0].jogos[0]
    assert item.meus_pontos == 9


def test_meus_pontos_none_quando_sem_palpite(db_session: Session) -> None:
    """meus_pontos é None quando o usuário não palpitou naquele jogo."""
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada, status=STATUS_ENCERRADO, gols_casa=1, gols_visitante=0)
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    # Outro usuário palpitou, mas Bernardo não.
    outro = _seed_usuario(db_session, "Thiago", "thiago")
    _seed_palpite(db_session, outro, jogo, pontos=3)
    db_session.commit()

    dados = listar_todos_os_jogos(db_session, usuario)

    assert len(dados.grupos) == 1
    item = dados.grupos[0].jogos[0]
    assert item.meus_pontos is None


def test_meus_pontos_zero_quando_palpite_com_zero_pontos(db_session: Session) -> None:
    """Palpite com 0 pontos é diferente de ausente: meus_pontos deve ser 0, não None."""
    rodada = _seed_rodada(db_session)
    jogo = _seed_jogo(db_session, rodada, status=STATUS_ENCERRADO, gols_casa=1, gols_visitante=0)
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    _seed_palpite(db_session, usuario, jogo, gols_casa=0, gols_visitante=1, pontos=0)
    db_session.commit()

    dados = listar_todos_os_jogos(db_session, usuario)

    item = dados.grupos[0].jogos[0]
    assert item.meus_pontos == 0
    assert item.meus_pontos is not None


# ---------------------------------------------------------------------------
# Testes: agrupamento e ordenação
# ---------------------------------------------------------------------------


def test_grupos_ordenados_por_rodada_ordem(db_session: Session) -> None:
    """Grupos devem vir em ordem crescente de Rodada.ordem."""
    r3 = _seed_rodada(db_session, "3ª Rodada", ordem=3)
    r1 = _seed_rodada(db_session, "1ª Rodada", ordem=1)
    r2 = _seed_rodada(db_session, "2ª Rodada", ordem=2)

    _seed_jogo(db_session, r3)
    _seed_jogo(db_session, r1, time_casa="Brasil", time_visitante="Alemanha")
    _seed_jogo(db_session, r2, time_casa="Argentina", time_visitante="França")

    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    dados = listar_todos_os_jogos(db_session, usuario)

    ordens = [g.ordem for g in dados.grupos]
    assert ordens == sorted(ordens)
    assert ordens == [1, 2, 3]


def test_jogos_dentro_de_grupo_ordenados_por_data_hora(db_session: Session) -> None:
    """Jogos dentro de cada rodada ordenados por data_hora asc."""
    rodada = _seed_rodada(db_session)
    j_tarde = _seed_jogo(
        db_session, rodada, time_casa="A", time_visitante="B",
        data_hora=_AGORA + timedelta(hours=5),
    )
    j_cedo = _seed_jogo(
        db_session, rodada, time_casa="C", time_visitante="D",
        data_hora=_AGORA + timedelta(hours=1),
    )
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    dados = listar_todos_os_jogos(db_session, usuario)

    jogos = dados.grupos[0].jogos
    assert len(jogos) == 2
    assert jogos[0].id == j_cedo.id
    assert jogos[1].id == j_tarde.id


# ---------------------------------------------------------------------------
# Testes: escudos
# ---------------------------------------------------------------------------


def test_escudo_presente_quando_alias_existe(db_session: Session) -> None:
    """Escudo correto quando team_alias tem escudo_url."""
    rodada = _seed_rodada(db_session)
    _seed_jogo(db_session, rodada, time_casa="Brasil", time_visitante="México")
    _seed_alias(
        db_session, "BRA", "Brasil",
        "https://a.espncdn.com/i/teamlogos/countries/500/bra.png",
    )
    _seed_alias(
        db_session, "MEX", "México",
        "https://a.espncdn.com/i/teamlogos/countries/500/mex.png",
    )
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    dados = listar_todos_os_jogos(db_session, usuario)
    item = dados.grupos[0].jogos[0]

    assert item.escudo_casa == "https://a.espncdn.com/i/teamlogos/countries/500/bra.png"
    assert item.escudo_visitante == "https://a.espncdn.com/i/teamlogos/countries/500/mex.png"


def test_escudo_none_quando_alias_ausente(db_session: Session) -> None:
    """escudo_casa/visitante são None quando não há team_alias; não quebra."""
    rodada = _seed_rodada(db_session)
    _seed_jogo(db_session, rodada, time_casa="TimeX", time_visitante="TimeY")
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    dados = listar_todos_os_jogos(db_session, usuario)
    item = dados.grupos[0].jogos[0]

    assert item.escudo_casa is None
    assert item.escudo_visitante is None


def test_escudo_none_quando_escudo_url_nao_populado(db_session: Session) -> None:
    """escudo_casa/visitante são None quando team_alias existe mas escudo_url é None."""
    rodada = _seed_rodada(db_session)
    _seed_jogo(db_session, rodada, time_casa="Argélia", time_visitante="Senegal")
    _seed_alias(db_session, "ALG", "Argélia", escudo_url=None)
    _seed_alias(db_session, "SEN", "Senegal", escudo_url=None)
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    dados = listar_todos_os_jogos(db_session, usuario)
    item = dados.grupos[0].jogos[0]

    assert item.escudo_casa is None
    assert item.escudo_visitante is None


# ---------------------------------------------------------------------------
# Testes: privacidade — não vaza pontos/palpites de terceiros
# ---------------------------------------------------------------------------


def test_lista_nao_vaza_pontos_de_terceiros_rodada_aberta(db_session: Session) -> None:
    """Com rodada aberta, meus_pontos reflete APENAS os pontos do próprio usuário."""
    rodada = _seed_rodada(
        db_session,
        aberta=True,
        abertura=_AGORA - timedelta(hours=2),
        fechamento=_AGORA + timedelta(hours=48),
    )
    jogo = _seed_jogo(db_session, rodada)
    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")

    # Thiago palpitou com 9 pontos; Bernardo com 3 pontos.
    _seed_palpite(db_session, thiago, jogo, gols_casa=2, gols_visitante=1, pontos=9)
    _seed_palpite(db_session, bernardo, jogo, gols_casa=1, gols_visitante=0, pontos=3)
    db_session.commit()

    # Bernardo vê os próprios 3 pontos — não os 9 de Thiago.
    dados = listar_todos_os_jogos(db_session, bernardo)
    item = dados.grupos[0].jogos[0]
    assert item.meus_pontos == 3


def test_lista_nao_vaza_pontos_de_terceiros_sem_palpite_proprio(db_session: Session) -> None:
    """Usuário sem palpite vê None, mesmo que outro usuário tenha pontos no jogo."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo = _seed_jogo(db_session, rodada)
    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")

    _seed_palpite(db_session, thiago, jogo, pontos=9)
    db_session.commit()

    # Bernardo não palpitou; deve ver None.
    dados = listar_todos_os_jogos(db_session, bernardo)
    item = dados.grupos[0].jogos[0]
    assert item.meus_pontos is None


# ---------------------------------------------------------------------------
# Testes: rota GET /jogos
# ---------------------------------------------------------------------------


def test_get_jogos_redireciona_sem_login(client: TestClient, db_session: Session) -> None:
    """Anônimo deve ser redirecionado para /login."""
    _seed_rodada(db_session)
    db_session.commit()

    response = client.get("/jogos", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_get_jogos_ok_com_login(client: TestClient, db_session: Session) -> None:
    """Usuário autenticado recebe 200 e vê o nome dos jogos na página."""
    rodada = _seed_rodada(db_session, aberta=False)
    _seed_jogo(db_session, rodada, time_casa="Brasil", time_visitante="Alemanha")
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    _login(client, "bernardo")
    response = client.get("/jogos")

    assert response.status_code == 200
    assert "Brasil" in response.text
    assert "Alemanha" in response.text


def test_get_jogos_pagina_vazia_sem_jogos(client: TestClient, db_session: Session) -> None:
    """Página lista de jogos deve renderizar mesmo sem nenhum jogo cadastrado."""
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    _login(client, "bernardo")
    response = client.get("/jogos")

    assert response.status_code == 200


def test_get_jogos_nao_conflita_com_get_jogo_detalhe(
    client: TestClient, db_session: Session
) -> None:
    """GET /jogos e GET /jogos/{id} devem coexistir sem conflito de rota."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo = _seed_jogo(db_session, rodada, time_casa="Brasil", time_visitante="Sérvia")
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    _login(client, "bernardo")
    resp_lista = client.get("/jogos")
    resp_detalhe = client.get(f"/jogos/{jogo.id}")

    assert resp_lista.status_code == 200
    assert resp_detalhe.status_code == 200


def test_get_jogos_mostra_pontos_proprios(client: TestClient, db_session: Session) -> None:
    """GET /jogos deve exibir os pontos do próprio usuário no HTML."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo = _seed_jogo(
        db_session, rodada, status=STATUS_ENCERRADO,
        gols_casa=2, gols_visitante=0,
        time_casa="Brasil", time_visitante="Sérvia",
    )
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    _seed_palpite(db_session, usuario, jogo, gols_casa=2, gols_visitante=0, pontos=9)
    db_session.commit()

    _login(client, "bernardo")
    response = client.get("/jogos")

    assert response.status_code == 200
    # 9 pontos devem aparecer na página do próprio usuário.
    assert "9" in response.text
