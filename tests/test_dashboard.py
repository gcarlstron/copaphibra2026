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
from app.services.dashboard import STATUS_AGENDADO, STATUS_ENCERRADO, montar_dashboard

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AGORA = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'dashboard.db'}",
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


def _seed_usuario(db: Session, nome: str, username: str, ativo: bool = True) -> Usuario:
    u = Usuario(
        nome=nome,
        username=username,
        senha_hash=hash_senha("1234"),
        is_admin=False,
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
    time_casa: str,
    time_visitante: str,
    data_hora: datetime,
    status: str = STATUS_AGENDADO,
    gols_casa: int | None = None,
    gols_visitante: int | None = None,
) -> Jogo:
    j = Jogo(
        rodada_id=rodada.id,
        data_hora=data_hora,
        time_casa=time_casa,
        time_visitante=time_visitante,
        status=status,
        gols_casa=gols_casa,
        gols_visitante=gols_visitante,
    )
    db.add(j)
    db.flush()
    return j


def _seed_palpite(db: Session, usuario: Usuario, jogo: Jogo, pontos: int) -> Palpite:
    p = Palpite(
        usuario_id=usuario.id,
        jogo_id=jogo.id,
        gols_casa=1,
        gols_visitante=0,
        pontos=pontos,
    )
    db.add(p)
    db.flush()
    return p


# ---------------------------------------------------------------------------
# Testes: classificação
# ---------------------------------------------------------------------------


def test_classificacao_ordenada_por_total(db_session: Session) -> None:
    rodada = _seed_rodada(db_session, aberta=False)
    jogo1 = _seed_jogo(db_session, rodada, "A", "B", _AGORA - timedelta(days=2), STATUS_ENCERRADO, 1, 0)
    jogo2 = _seed_jogo(db_session, rodada, "C", "D", _AGORA - timedelta(days=1), STATUS_ENCERRADO, 2, 0)

    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")

    # Bernardo: 9 + 6 = 15
    _seed_palpite(db_session, bernardo, jogo1, 9)
    _seed_palpite(db_session, bernardo, jogo2, 6)

    # Thiago: 3 + 3 = 6
    _seed_palpite(db_session, thiago, jogo1, 3)
    _seed_palpite(db_session, thiago, jogo2, 3)

    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    nomes = [item.nome for item in dados.classificacao]

    assert nomes[0] == "Bernardo"
    assert nomes[1] == "Thiago"
    assert dados.classificacao[0].total == 15
    assert dados.classificacao[1].total == 6


def test_classificacao_desempate_por_qtd_9(db_session: Session) -> None:
    """Dois jogadores com o mesmo total; quem tem mais 9pts vai à frente."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo1 = _seed_jogo(db_session, rodada, "A", "B", _AGORA - timedelta(days=2), STATUS_ENCERRADO, 1, 0)
    jogo2 = _seed_jogo(db_session, rodada, "C", "D", _AGORA - timedelta(days=1), STATUS_ENCERRADO, 2, 0)

    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")

    # Ambos 12 pontos, mas Bernardo tem 9+3 e Thiago tem 6+6.
    _seed_palpite(db_session, bernardo, jogo1, 9)
    _seed_palpite(db_session, bernardo, jogo2, 3)

    _seed_palpite(db_session, thiago, jogo1, 6)
    _seed_palpite(db_session, thiago, jogo2, 6)

    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert dados.classificacao[0].nome == "Bernardo"
    assert dados.classificacao[0].total == 12
    assert dados.classificacao[1].nome == "Thiago"


def test_classificacao_desempate_por_qtd_6_quando_9_igual(db_session: Session) -> None:
    """Mesmo total e mesmo qtd_9; quem tem mais 6pts vai à frente."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo1 = _seed_jogo(db_session, rodada, "A", "B", _AGORA - timedelta(days=3), STATUS_ENCERRADO, 1, 0)
    jogo2 = _seed_jogo(db_session, rodada, "C", "D", _AGORA - timedelta(days=2), STATUS_ENCERRADO, 2, 0)
    jogo3 = _seed_jogo(db_session, rodada, "E", "F", _AGORA - timedelta(days=1), STATUS_ENCERRADO, 3, 0)

    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")

    # Ambos: total = 15, qtd_9 = 1.
    # Bernardo: 9 + 6 + 0 = 15, qtd_6 = 1
    _seed_palpite(db_session, bernardo, jogo1, 9)
    _seed_palpite(db_session, bernardo, jogo2, 6)
    _seed_palpite(db_session, bernardo, jogo3, 0)

    # Thiago: 9 + 3 + 3 = 15, qtd_6 = 0
    _seed_palpite(db_session, thiago, jogo1, 9)
    _seed_palpite(db_session, thiago, jogo2, 3)
    _seed_palpite(db_session, thiago, jogo3, 3)

    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert dados.classificacao[0].nome == "Bernardo"
    assert dados.classificacao[1].nome == "Thiago"


def test_classificacao_empate_real_mesma_posicao(db_session: Session) -> None:
    """Jogadores com chave idêntica recebem a mesma posição."""
    rodada = _seed_rodada(db_session, aberta=False)
    jogo1 = _seed_jogo(db_session, rodada, "A", "B", _AGORA - timedelta(days=1), STATUS_ENCERRADO, 1, 0)

    bernardo = _seed_usuario(db_session, "Bernardo", "bernardo")
    thiago = _seed_usuario(db_session, "Thiago", "thiago")

    # Ambos com exatamente a mesma pontuação.
    _seed_palpite(db_session, bernardo, jogo1, 9)
    _seed_palpite(db_session, thiago, jogo1, 9)

    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    posicoes = [item.posicao for item in dados.classificacao]
    assert posicoes[0] == posicoes[1] == 1


def test_classificacao_exclui_usuarios_inativos(db_session: Session) -> None:
    rodada = _seed_rodada(db_session, aberta=False)
    jogo1 = _seed_jogo(db_session, rodada, "A", "B", _AGORA - timedelta(days=1), STATUS_ENCERRADO, 1, 0)

    ativo = _seed_usuario(db_session, "Bernardo", "bernardo", ativo=True)
    inativo = _seed_usuario(db_session, "Fantasma", "fantasma", ativo=False)

    _seed_palpite(db_session, ativo, jogo1, 9)
    _seed_palpite(db_session, inativo, jogo1, 9)

    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    nomes = [item.nome for item in dados.classificacao]
    assert "Bernardo" in nomes
    assert "Fantasma" not in nomes
    assert len(dados.classificacao) == 1


def test_classificacao_sem_palpites_retorna_lista_com_zeros(db_session: Session) -> None:
    """Usuário ativo sem palpites aparece na classificação com total = 0."""
    _seed_usuario(db_session, "Bernardo", "bernardo", ativo=True)
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert len(dados.classificacao) == 1
    assert dados.classificacao[0].total == 0


# ---------------------------------------------------------------------------
# Testes: jogos recentes
# ---------------------------------------------------------------------------


def test_jogos_recentes_so_encerrados(db_session: Session) -> None:
    rodada = _seed_rodada(db_session, aberta=False)
    _seed_jogo(db_session, rodada, "A", "B", _AGORA - timedelta(days=1), STATUS_ENCERRADO, 1, 0)
    _seed_jogo(db_session, rodada, "C", "D", _AGORA + timedelta(days=1), STATUS_AGENDADO)
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert len(dados.jogos_recentes) == 1
    assert dados.jogos_recentes[0].status == STATUS_ENCERRADO


def test_jogos_recentes_ordem_desc_por_data(db_session: Session) -> None:
    rodada = _seed_rodada(db_session, aberta=False)
    mais_antigo = _seed_jogo(db_session, rodada, "A", "B", _AGORA - timedelta(days=3), STATUS_ENCERRADO, 1, 0)
    mais_recente = _seed_jogo(db_session, rodada, "C", "D", _AGORA - timedelta(days=1), STATUS_ENCERRADO, 2, 1)
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert dados.jogos_recentes[0].jogo_id == mais_recente.id
    assert dados.jogos_recentes[1].jogo_id == mais_antigo.id


def test_jogos_recentes_limite_5(db_session: Session) -> None:
    rodada = _seed_rodada(db_session, aberta=False)
    for i in range(7):
        _seed_jogo(
            db_session,
            rodada,
            f"T{i}",
            f"T{i+10}",
            _AGORA - timedelta(days=i + 1),
            STATUS_ENCERRADO,
            1,
            0,
        )
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert len(dados.jogos_recentes) == 5


# ---------------------------------------------------------------------------
# Testes: próximos jogos
# ---------------------------------------------------------------------------


def test_proximos_jogos_so_agendados(db_session: Session) -> None:
    rodada = _seed_rodada(db_session, aberta=True, abertura=_AGORA - timedelta(hours=1))
    _seed_jogo(db_session, rodada, "A", "B", _AGORA + timedelta(days=1), STATUS_AGENDADO)
    _seed_jogo(db_session, rodada, "C", "D", _AGORA - timedelta(days=1), STATUS_ENCERRADO, 1, 0)
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert len(dados.proximos_jogos) == 1
    assert dados.proximos_jogos[0].status == STATUS_AGENDADO


def test_proximos_jogos_ordem_asc_por_data(db_session: Session) -> None:
    rodada = _seed_rodada(db_session, aberta=True, abertura=_AGORA - timedelta(hours=1))
    mais_longe = _seed_jogo(db_session, rodada, "A", "B", _AGORA + timedelta(days=3), STATUS_AGENDADO)
    mais_proximo = _seed_jogo(db_session, rodada, "C", "D", _AGORA + timedelta(days=1), STATUS_AGENDADO)
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert dados.proximos_jogos[0].jogo_id == mais_proximo.id
    assert dados.proximos_jogos[1].jogo_id == mais_longe.id


def test_proximos_jogos_limite_5(db_session: Session) -> None:
    rodada = _seed_rodada(db_session, aberta=True, abertura=_AGORA - timedelta(hours=1))
    for i in range(7):
        _seed_jogo(
            db_session,
            rodada,
            f"T{i}",
            f"T{i+10}",
            _AGORA + timedelta(days=i + 1),
            STATUS_AGENDADO,
        )
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert len(dados.proximos_jogos) == 5


# ---------------------------------------------------------------------------
# Testes: rodadas abertas
# ---------------------------------------------------------------------------


def test_rodadas_abertas_listadas(db_session: Session) -> None:
    _seed_rodada(
        db_session,
        nome="1ª Rodada",
        ordem=1,
        aberta=True,
        abertura=_AGORA - timedelta(hours=2),
        fechamento=_AGORA + timedelta(hours=2),
    )
    _seed_rodada(db_session, nome="2ª Rodada", ordem=2, aberta=False)
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert len(dados.rodadas_abertas) == 1
    assert dados.rodadas_abertas[0].nome == "1ª Rodada"


def test_rodada_fechada_nao_listada_apos_fechamento(db_session: Session) -> None:
    _seed_rodada(
        db_session,
        nome="1ª Rodada",
        ordem=1,
        aberta=True,
        abertura=_AGORA - timedelta(hours=4),
        fechamento=_AGORA - timedelta(hours=1),  # já fechou
    )
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert len(dados.rodadas_abertas) == 0


def test_rodada_aberta_sem_janela_listada(db_session: Session) -> None:
    """Rodada aberta sem janela de datas deve aparecer como aberta."""
    _seed_rodada(db_session, nome="1ª Rodada", ordem=1, aberta=True)
    db_session.commit()

    dados = montar_dashboard(db_session, _AGORA)
    assert len(dados.rodadas_abertas) == 1


# ---------------------------------------------------------------------------
# Testes: rota GET / (autenticação)
# ---------------------------------------------------------------------------


def test_get_dashboard_redireciona_sem_login(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_get_dashboard_ok_com_login(client: TestClient, db_session: Session) -> None:
    usuario = _seed_usuario(db_session, "Bernardo", "bernardo")
    db_session.commit()

    response = client.post(
        "/login",
        data={"username": "bernardo", "senha": "1234"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    response = client.get("/")
    assert response.status_code == 200
    # Garante que a página renderizou com algo da classificação.
    assert "Classificação" in response.text
