"""Tests for login + ESPN sync integration (Fase 10e).

Verifica que:
- Login funciona mesmo se ESPN falhar
- O login dispara o sync como BackgroundTask
- Login com credenciais erradas não dispara sync
- A BackgroundTask recebe uma factory de sessão e um datetime
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import create_app
from app.models import Usuario
from app.services.auth import hash_senha
from app.services.sync_resultados import ResumoSync

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AGORA = datetime(2026, 6, 11, 20, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'login_sync.db'}",
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


def _seed_usuario(db: Session, username: str = "user1", senha: str = "senha123") -> Usuario:
    u = Usuario(
        nome="Jogador",
        username=username,
        senha_hash=hash_senha(senha),
        ativo=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


class TestLoginComSync:
    def test_login_ok_mesmo_com_espn_falhando(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Login deve funcionar mesmo que sincronizar_resultados lance exceção.

        A exceção é absovida dentro de disparar_sync_se_necessario pelo try/except
        amplo — nunca deve propagar para o BackgroundTask e quebrar o login.
        """
        _seed_usuario(db_session)

        # Deixa disparar_sync_se_necessario rodar de verdade (com sua sessão própria),
        # mas faz sincronizar_resultados falhar — o try/except interno deve absorver.
        with patch(
            "app.services.sync_resultados.sincronizar_resultados",
            side_effect=RuntimeError("ESPN caiu"),
        ):
            resp = client.post(
                "/login",
                data={"username": "user1", "senha": "senha123"},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    def test_login_redireciona_para_dashboard(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Login bem-sucedido deve redirecionar para /."""
        _seed_usuario(db_session)

        with patch(
            "app.routers.auth.disparar_sync_se_necessario", return_value=None
        ):
            resp = client.post(
                "/login",
                data={"username": "user1", "senha": "senha123"},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    def test_login_credenciais_erradas_nao_dispara_sync(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Login com senha errada não deve disparar o sync."""
        _seed_usuario(db_session)

        mock_disparar = MagicMock()
        with patch("app.routers.auth.disparar_sync_se_necessario", mock_disparar):
            resp = client.post(
                "/login",
                data={"username": "user1", "senha": "errada"},
                follow_redirects=False,
            )

        assert resp.status_code == 401
        mock_disparar.assert_not_called()

    def test_sync_usa_sessao_propria(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Verifica que disparar_sync_se_necessario recebe uma factory de sessão."""
        _seed_usuario(db_session)

        captured_args: list = []

        def _fake_disparar(db_factory, agora):
            captured_args.append((db_factory, agora))

        with patch("app.routers.auth.disparar_sync_se_necessario", _fake_disparar):
            resp = client.post(
                "/login",
                data={"username": "user1", "senha": "senha123"},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        # TestClient executa BackgroundTasks sincronamente
        assert len(captured_args) == 1
        db_factory, agora = captured_args[0]
        # db_factory deve ser chamável (SessionLocal)
        assert callable(db_factory)
        assert isinstance(agora, datetime)

    def test_sync_dispara_no_login_bem_sucedido(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Login bem-sucedido deve adicionar o sync como BackgroundTask."""
        _seed_usuario(db_session)

        mock_disparar = MagicMock()
        with patch("app.routers.auth.disparar_sync_se_necessario", mock_disparar):
            resp = client.post(
                "/login",
                data={"username": "user1", "senha": "senha123"},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        # TestClient roda BackgroundTasks inline
        mock_disparar.assert_called_once()


# ---------------------------------------------------------------------------
# Throttle tests — verificados em test_sync_resultados.py com sessão isolada
# Os testes abaixo cobrem o comportamento de throttle a nível de BackgroundTask
# ---------------------------------------------------------------------------


class TestThrottleViaDispararSync:
    """Testa o throttle diretamente em disparar_sync_se_necessario com sessão controlada."""

    def _make_factory(self, db_session: Session):
        def factory():
            return db_session
        return factory

    def test_throttle_dentro_da_janela_nao_chama_sync(
        self, db_session: Path
    ) -> None:
        """Segunda chamada dentro da janela não deve executar o sync."""
        from app.models.sync_state import SyncState
        from app.services.sync_resultados import CHAVE_SYNC, disparar_sync_se_necessario

        estado = SyncState(chave=CHAVE_SYNC, ultima_execucao=_AGORA)
        db_session.add(estado)
        db_session.commit()

        mock_sync = MagicMock(return_value=ResumoSync())
        factory = self._make_factory(db_session)

        from datetime import timedelta

        agora2 = _AGORA + timedelta(minutes=5)  # dentro da janela de 15 min
        with patch(
            "app.services.sync_resultados.sincronizar_resultados", mock_sync
        ), patch(
            "app.services.sync_resultados.get_settings",
            return_value=MagicMock(espn_sync_intervalo_min=15, espn_timeout_s=5),
        ):
            disparar_sync_se_necessario(factory, agora2)

        mock_sync.assert_not_called()

    def test_throttle_apos_janela_chama_sync(self, db_session: Session) -> None:
        """Após a janela de throttle, o sync deve ser chamado."""
        from datetime import timedelta

        from app.models.sync_state import SyncState
        from app.services.sync_resultados import CHAVE_SYNC, disparar_sync_se_necessario

        execucao_antiga = _AGORA - timedelta(minutes=20)
        estado = SyncState(chave=CHAVE_SYNC, ultima_execucao=execucao_antiga)
        db_session.add(estado)
        db_session.commit()

        mock_sync = MagicMock(return_value=ResumoSync())
        factory = self._make_factory(db_session)

        with patch(
            "app.services.sync_resultados.sincronizar_resultados", mock_sync
        ), patch(
            "app.services.sync_resultados.get_settings",
            return_value=MagicMock(espn_sync_intervalo_min=15, espn_timeout_s=5),
        ):
            disparar_sync_se_necessario(factory, _AGORA)

        mock_sync.assert_called_once()
