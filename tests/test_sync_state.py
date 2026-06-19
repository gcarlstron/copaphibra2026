"""Tests for SyncState model (Fase 10a).

Verifica:
- get-or-create da linha (chave única)
- Leitura/escrita do timestamp ultima_execucao
- Chave única é enforced
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.sync_state import SyncState
from app.services.sync_resultados import CHAVE_SYNC, _get_or_create_sync_state

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'sync_state.db'}",
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


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

_AGORA = datetime(2026, 6, 11, 20, 0, 0, tzinfo=timezone.utc)


class TestSyncState:
    def test_cria_se_nao_existe(self, db_session: Session) -> None:
        """_get_or_create_sync_state deve criar a linha na primeira chamada."""
        estado = _get_or_create_sync_state(db_session, CHAVE_SYNC)
        assert estado is not None
        assert estado.chave == CHAVE_SYNC
        assert estado.ultima_execucao is None

    def test_get_or_create_idempotente(self, db_session: Session) -> None:
        """Chamar duas vezes não deve duplicar a linha."""
        e1 = _get_or_create_sync_state(db_session, CHAVE_SYNC)
        e2 = _get_or_create_sync_state(db_session, CHAVE_SYNC)
        assert e1.id == e2.id

        count = len(
            db_session.execute(
                select(SyncState).where(SyncState.chave == CHAVE_SYNC)
            ).all()
        )
        assert count == 1

    def test_grava_e_le_timestamp(self, db_session: Session) -> None:
        """Deve ser possível gravar e ler ultima_execucao."""
        estado = _get_or_create_sync_state(db_session, CHAVE_SYNC)
        assert estado.ultima_execucao is None

        estado.ultima_execucao = _AGORA
        db_session.commit()

        recarregado = db_session.scalar(
            select(SyncState).where(SyncState.chave == CHAVE_SYNC)
        )
        assert recarregado is not None
        assert recarregado.ultima_execucao is not None
        # Compara como UTC (SQLite guarda sem tz; reinterpretamos)
        ts = recarregado.ultima_execucao
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        assert ts == _AGORA

    def test_chave_unica(self, db_session: Session) -> None:
        """Duas linhas com a mesma chave devem violar unique constraint."""
        from sqlalchemy.exc import IntegrityError

        db_session.add(SyncState(chave="teste", ultima_execucao=None))
        db_session.commit()
        db_session.add(SyncState(chave="teste", ultima_execucao=None))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_chaves_diferentes_coexistem(self, db_session: Session) -> None:
        """Chaves distintas devem coexistir sem conflito."""
        db_session.add(SyncState(chave="chave_a", ultima_execucao=None))
        db_session.add(SyncState(chave="chave_b", ultima_execucao=None))
        db_session.commit()

        rows = db_session.execute(select(SyncState)).scalars().all()
        assert len(rows) == 2
