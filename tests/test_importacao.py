"""Testa o importador da planilha em banco temporário.

Requer o arquivo .xlsx em import/. Se não existir, o teste é pulado para não
quebrar o CI sem a planilha.

Execução:
    pytest tests/test_importacao.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Verifica se a planilha existe; se não, pula todos os testes deste módulo.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_XLSX_PATH = _PROJECT_ROOT / "import" / "COPA PHIBRA 2026 OFICIAL ATÉ A FINAL SEGUNDA FASE.xlsx"

pytestmark = pytest.mark.skipif(
    not _XLSX_PATH.exists(),
    reason=f"Planilha não encontrada: {_XLSX_PATH}",
)


# ---------------------------------------------------------------------------
# Fixture: banco temporário isolado para o importador
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def db_importado(tmp_path_factory: pytest.TempPathFactory):
    """Cria um banco SQLite temporário, roda o importador e devolve uma sessão.

    Injeta o engine/session_factory diretamente em importar() para evitar
    qualquer colisão com o banco de produção ou com outros módulos já
    carregados em memória.
    """
    from app.database import Base
    from app.models import Jogo, Palpite, Rodada, Usuario  # registra no metadata

    tmp_dir = tmp_path_factory.mktemp("importacao_db")
    db_file = tmp_dir / "copa_phibra_test.db"
    db_url = f"sqlite:///{db_file}"

    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    # Cria as tabelas no banco temporário
    Base.metadata.create_all(bind=test_engine)

    # Chama o importador injetando o session_factory do banco temporário
    from scripts.importar_planilha import importar

    importar(senha="senhateste123", session_factory=TestSessionLocal, xlsx_path=_XLSX_PATH)

    db = TestSessionLocal()
    yield db
    db.close()
    test_engine.dispose()


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

ESPERADO: dict[str, int] = {
    "Bernardo": 44,
    "Thiago": 47,
    "Ricardo": 47,
    "Fernando": 40,
    "Gustavo": 48,
    "Marcio": 67,
    "Gabriel": 34,
    "Renan": 26,
    "Soares": 48,
    "Marques": 63,
}

NOMES_JOGADORES = list(ESPERADO.keys())


def test_rodadas_importadas(db_importado) -> None:
    """Devem existir exatamente 3 rodadas com ordens 1, 2 e 3."""
    from app.models import Rodada

    rodadas = db_importado.execute(select(Rodada).order_by(Rodada.ordem)).scalars().all()
    assert len(rodadas) == 3
    assert [r.ordem for r in rodadas] == [1, 2, 3]
    assert all(r.aberta is False for r in rodadas)


def test_jogos_importados(db_importado) -> None:
    """Devem existir exatamente 72 jogos (24 por rodada × 3 rodadas)."""
    from app.models import Jogo

    total = db_importado.execute(select(func.count()).select_from(Jogo)).scalar_one()
    assert total == 72


def test_jogos_com_resultado_primeira_rodada(db_importado) -> None:
    """Os primeiros 22 jogos da 1ª rodada devem ter status ENCERRADO."""
    from app.models import Jogo, Rodada
    from app.services.dashboard import STATUS_ENCERRADO

    rodada1 = db_importado.execute(
        select(Rodada).where(Rodada.ordem == 1)
    ).scalar_one()
    jogos_enc = (
        db_importado.execute(
            select(Jogo).where(
                Jogo.rodada_id == rodada1.id,
                Jogo.status == STATUS_ENCERRADO,
            )
        )
        .scalars()
        .all()
    )
    # Apenas as 22 primeiras linhas (2–23) têm resultado na planilha
    assert len(jogos_enc) == 22


def test_usuarios_importados(db_importado) -> None:
    """Devem existir 10 usuários jogadores (não admin)."""
    from app.models import Usuario

    jogadores = (
        db_importado.execute(
            select(Usuario).where(Usuario.is_admin == False)  # noqa: E712
        )
        .scalars()
        .all()
    )
    assert len(jogadores) == 10
    nomes = sorted(u.nome for u in jogadores)
    assert nomes == sorted(NOMES_JOGADORES)


@pytest.mark.parametrize("nome", NOMES_JOGADORES)
def test_total_pontos_por_jogador(db_importado, nome: str) -> None:
    """Total de pontos de cada jogador deve bater com o esperado da planilha."""
    from app.models import Jogo, Palpite, Usuario
    from app.services.dashboard import STATUS_ENCERRADO

    usuario = db_importado.execute(
        select(Usuario).where(Usuario.nome == nome)
    ).scalar_one()

    rows = db_importado.execute(
        select(Palpite.pontos)
        .join(Jogo, Palpite.jogo_id == Jogo.id)
        .where(
            Palpite.usuario_id == usuario.id,
            Jogo.status == STATUS_ENCERRADO,
        )
    ).all()

    total = sum(r[0] for r in rows)
    assert total == ESPERADO[nome], f"{nome}: esperado {ESPERADO[nome]}, obtido {total}"


def test_palpites_terceira_rodada_ausentes(db_importado) -> None:
    """Nenhum jogador deve ter palpites na 3ª rodada (planilha em branco)."""
    from app.models import Jogo, Palpite, Rodada

    rodada3 = db_importado.execute(
        select(Rodada).where(Rodada.ordem == 3)
    ).scalar_one()

    jogos_r3 = db_importado.execute(
        select(Jogo.id).where(Jogo.rodada_id == rodada3.id)
    ).scalars().all()

    palpites = (
        db_importado.execute(
            select(Palpite).where(Palpite.jogo_id.in_(jogos_r3))
        )
        .scalars()
        .all()
    )

    assert len(palpites) == 0, "Não deveria haver palpites na 3ª rodada"
