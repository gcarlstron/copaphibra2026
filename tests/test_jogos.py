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
from app.services.jogos import detalhe_do_jogo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AGORA = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jogos.db'}",
        connect_args={"check_same_thread": False},
    )
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
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helpers de seed
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


def _login(client: TestClient, username: str, senha: str = "1234") -> None:
    resp = client.post("/login", data={"username": username, "senha": senha}, follow_redirects=False)
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Testes: serviço — privacidade com rodada ABERTA
# ---------------------------------------------------------------------------


def test_rodada_aberta_usuario_nao_ve_palpites_de_terceiros(db_session: Session) -> None:
    """Com rodada aberta, terceiros_visiveis=False; o usuário vê só o próprio palpite."""
    rodada = _seed_rodada(
        db_session,
        aberta=True,
        abertura=_AGORA - timedelta(hours=2),
        fechamento=_AGORA + timedelta(hours=2),  # ainda aberta em _AGORA
    )
    jogo = _seed_jogo(db_session, rodada)

    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")

    _seed_palpite(db_session, bernardo, jogo, gols_casa=2, gols_visitante=1, pontos=9)
    _seed_palpite(db_session, thiago, jogo, gols_casa=1, gols_visitante=0, pontos=3)
    db_session.commit()

    dados = detalhe_do_jogo(db_session, jogo.id, thiago, _AGORA)

    assert dados.terceiros_visiveis is False
    # Thiago só vê o próprio palpite.
    assert len(dados.palpites) == 1
    assert dados.palpites[0].nome == "Thiago"


def test_rodada_aberta_usuario_sem_palpite_ve_lista_vazia(db_session: Session) -> None:
    """Com rodada aberta e sem palpite próprio, retorna lista vazia."""
    rodada = _seed_rodada(
        db_session,
        aberta=True,
        abertura=_AGORA - timedelta(hours=2),
        fechamento=_AGORA + timedelta(hours=2),
    )
    jogo = _seed_jogo(db_session, rodada)
    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")

    # Bernardo palpitou, Thiago não.
    _seed_palpite(db_session, bernardo, jogo, pontos=9)
    db_session.commit()

    dados = detalhe_do_jogo(db_session, jogo.id, thiago, _AGORA)

    assert dados.terceiros_visiveis is False
    assert dados.palpites == []


# ---------------------------------------------------------------------------
# Testes: serviço — privacidade com rodada FECHADA
# ---------------------------------------------------------------------------


def test_rodada_fechada_usuario_ve_todos_os_palpites_ativos(db_session: Session) -> None:
    """Com rodada fechada, terceiros_visiveis=True; o usuário vê todos de ativos."""
    rodada = _seed_rodada(
        db_session,
        aberta=True,
        abertura=_AGORA - timedelta(hours=4),
        fechamento=_AGORA - timedelta(hours=1),  # já fechou antes de _AGORA
    )
    jogo = _seed_jogo(db_session, rodada, status=STATUS_ENCERRADO, gols_casa=2, gols_visitante=1)

    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")

    _seed_palpite(db_session, bernardo, jogo, gols_casa=2, gols_visitante=1, pontos=9)
    _seed_palpite(db_session, thiago, jogo, gols_casa=1, gols_visitante=0, pontos=3)
    db_session.commit()

    dados = detalhe_do_jogo(db_session, jogo.id, thiago, _AGORA)

    assert dados.terceiros_visiveis is True
    nomes = {p.nome for p in dados.palpites}
    assert "Bernardo" in nomes
    assert "Thiago" in nomes


# ---------------------------------------------------------------------------
# Testes: serviço — usuários inativos não aparecem
# ---------------------------------------------------------------------------


def test_usuarios_inativos_nao_aparecem_na_lista(db_session: Session) -> None:
    """Usuários com ativo=False são excluídos mesmo quando terceiros_visiveis=True."""
    rodada = _seed_rodada(
        db_session,
        aberta=True,
        abertura=_AGORA - timedelta(hours=4),
        fechamento=_AGORA - timedelta(hours=1),
    )
    jogo = _seed_jogo(db_session, rodada, status=STATUS_ENCERRADO, gols_casa=1, gols_visitante=0)

    ativo = _seed_usuario(db_session, "Bernardo", "bernardo", ativo=True)
    inativo = _seed_usuario(db_session, "Fantasma", "fantasma", ativo=False)
    viewer = _seed_usuario(db_session, "Thiago", "thiago", ativo=True)

    _seed_palpite(db_session, ativo, jogo, gols_casa=1, gols_visitante=0, pontos=9)
    _seed_palpite(db_session, inativo, jogo, gols_casa=1, gols_visitante=0, pontos=9)
    _seed_palpite(db_session, viewer, jogo, gols_casa=0, gols_visitante=0, pontos=0)
    db_session.commit()

    dados = detalhe_do_jogo(db_session, jogo.id, viewer, _AGORA)

    assert dados.terceiros_visiveis is True
    nomes = [p.nome for p in dados.palpites]
    assert "Fantasma" not in nomes
    assert "Bernardo" in nomes


# ---------------------------------------------------------------------------
# Testes: serviço — ordenação por pontos desc
# ---------------------------------------------------------------------------


def test_palpites_ordenados_por_pontos_desc(db_session: Session) -> None:
    """Quando terceiros visíveis, a lista deve estar ordenada pontos desc."""
    rodada = _seed_rodada(
        db_session,
        aberta=True,
        abertura=_AGORA - timedelta(hours=4),
        fechamento=_AGORA - timedelta(hours=1),
    )
    jogo = _seed_jogo(db_session, rodada, status=STATUS_ENCERRADO, gols_casa=2, gols_visitante=1)

    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")
    ricardo = _seed_usuario(db_session, "Ricardo", "ricardo")

    _seed_palpite(db_session, bernardo, jogo, gols_casa=2, gols_visitante=1, pontos=9)
    _seed_palpite(db_session, thiago, jogo, gols_casa=2, gols_visitante=0, pontos=6)
    _seed_palpite(db_session, ricardo, jogo, gols_casa=1, gols_visitante=0, pontos=3)
    db_session.commit()

    dados = detalhe_do_jogo(db_session, jogo.id, thiago, _AGORA)

    assert dados.terceiros_visiveis is True
    pontos_lista = [p.pontos for p in dados.palpites]
    assert pontos_lista == sorted(pontos_lista, reverse=True)
    assert pontos_lista[0] == 9


# ---------------------------------------------------------------------------
# Testes: serviço — jogo inexistente
# ---------------------------------------------------------------------------


def test_jogo_inexistente_levanta_value_error(db_session: Session) -> None:
    """detalhe_do_jogo deve levantar ValueError para jogo_id inválido."""
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    with pytest.raises(ValueError, match="não encontrado"):
        detalhe_do_jogo(db_session, jogo_id=9999, usuario=usuario, agora=_AGORA)


# ---------------------------------------------------------------------------
# Testes: rota GET /jogos/{id} — autenticação e HTTP
# ---------------------------------------------------------------------------


def test_get_jogo_redireciona_sem_login(client: TestClient, db_session: Session) -> None:
    """Anônimo é redirecionado para /login."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo = _seed_jogo(db_session, rodada)
    db_session.commit()

    response = client.get(f"/jogos/{jogo.id}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_get_jogo_inexistente_retorna_404(client: TestClient, db_session: Session) -> None:
    """Jogo não encontrado deve retornar HTTP 404."""
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    _login(client, "bernardo")
    response = client.get("/jogos/9999")

    assert response.status_code == 404


def test_get_jogo_ok_com_login(client: TestClient, db_session: Session) -> None:
    """Usuário autenticado recebe a página com dados do jogo."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo = _seed_jogo(
        db_session,
        rodada,
        time_casa="Brasil",
        time_visitante="Argentina",
        status=STATUS_AGENDADO,
    )
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    _login(client, "bernardo")
    response = client.get(f"/jogos/{jogo.id}")

    assert response.status_code == 200
    assert "Brasil" in response.text
    assert "Argentina" in response.text


def test_get_jogo_palpites_visiveis_apos_fechamento(
    client: TestClient, db_session: Session
) -> None:
    """Após o fechamento da rodada, a tabela de palpites aparece no HTML.

    Usa timestamps relativos ao instante real de execução.
    """
    agora_real = datetime.now(timezone.utc)
    rodada = _seed_rodada(
        db_session,
        aberta=True,
        abertura=agora_real - timedelta(hours=4),
        fechamento=agora_real - timedelta(hours=1),  # já fechou
    )
    jogo = _seed_jogo(db_session, rodada, status=STATUS_ENCERRADO, gols_casa=1, gols_visitante=0)

    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")
    _seed_palpite(db_session, bernardo, jogo, gols_casa=1, gols_visitante=0, pontos=9)
    _seed_palpite(db_session, thiago, jogo, gols_casa=0, gols_visitante=0, pontos=0)
    db_session.commit()

    _login(client, "thiago")
    response = client.get(f"/jogos/{jogo.id}")

    assert response.status_code == 200
    # Ambos os nomes devem aparecer na tabela.
    assert "Bernardo" in response.text
    assert "Thiago" in response.text
    # Mensagem de bloqueio NÃO deve aparecer.
    assert "Palpites liberados" not in response.text


def test_get_jogo_palpites_bloqueados_com_rodada_aberta(
    client: TestClient, db_session: Session
) -> None:
    """Com rodada aberta, a mensagem de bloqueio aparece e palpites de terceiros não.

    Usa timestamps relativos ao instante real de execução para que a janela de
    fechamento ainda não tenha passado quando o router chama datetime.now().
    """
    agora_real = datetime.now(timezone.utc)
    rodada = _seed_rodada(
        db_session,
        aberta=True,
        abertura=agora_real - timedelta(hours=2),
        fechamento=agora_real + timedelta(hours=48),  # bem no futuro — garantidamente aberta
    )
    jogo = _seed_jogo(db_session, rodada)

    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")
    _seed_palpite(db_session, bernardo, jogo, gols_casa=2, gols_visitante=1, pontos=0)
    db_session.commit()

    _login(client, "thiago")
    response = client.get(f"/jogos/{jogo.id}")

    assert response.status_code == 200
    assert "Palpites liberados" in response.text
    # Bernardo não deve aparecer para Thiago enquanto rodada aberta.
    assert "Bernardo" not in response.text


# ---------------------------------------------------------------------------
# Testes Fase 11b — escudos no detalhe do jogo
# ---------------------------------------------------------------------------


def _seed_team_alias(
    db: Session,
    abrev: str,
    nome: str,
    escudo_url: str | None = None,
) -> TeamAlias:
    ta = TeamAlias(
        abreviacao=abrev,
        nome=nome,
        nome_en=nome,
        escudo_url=escudo_url,
    )
    db.add(ta)
    db.flush()
    return ta


def test_detalhe_traz_escudo_quando_alias_existe(db_session: Session) -> None:
    """detalhe_do_jogo preenche escudo_casa/visitante quando team_alias tem escudo_url."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo = _seed_jogo(
        db_session,
        rodada,
        time_casa="Brasil",
        time_visitante="México",
    )
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    _seed_team_alias(
        db_session,
        "BRA",
        "Brasil",
        "https://a.espncdn.com/i/teamlogos/countries/500/bra.png",
    )
    _seed_team_alias(
        db_session,
        "MEX",
        "México",
        "https://a.espncdn.com/i/teamlogos/countries/500/mex.png",
    )
    db_session.commit()

    dados = detalhe_do_jogo(db_session, jogo.id, usuario, _AGORA)

    assert dados.jogo.escudo_casa == "https://a.espncdn.com/i/teamlogos/countries/500/bra.png"
    assert dados.jogo.escudo_visitante == "https://a.espncdn.com/i/teamlogos/countries/500/mex.png"


def test_detalhe_escudo_none_quando_alias_ausente(db_session: Session) -> None:
    """detalhe_do_jogo retorna None para escudos quando time não tem team_alias."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo = _seed_jogo(
        db_session,
        rodada,
        time_casa="TimeX",
        time_visitante="TimeY",
    )
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    # Nenhum team_alias inserido — não deve quebrar.
    dados = detalhe_do_jogo(db_session, jogo.id, usuario, _AGORA)

    assert dados.jogo.escudo_casa is None
    assert dados.jogo.escudo_visitante is None


def test_detalhe_escudo_none_quando_escudo_url_nao_populado(db_session: Session) -> None:
    """detalhe_do_jogo retorna None quando team_alias existe mas escudo_url é None."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo = _seed_jogo(db_session, rodada, time_casa="Argentina", time_visitante="Alemanha")
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    _seed_team_alias(db_session, "ARG", "Argentina", escudo_url=None)
    _seed_team_alias(db_session, "GER", "Alemanha", escudo_url=None)
    db_session.commit()

    dados = detalhe_do_jogo(db_session, jogo.id, usuario, _AGORA)

    assert dados.jogo.escudo_casa is None
    assert dados.jogo.escudo_visitante is None
