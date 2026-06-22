"""Tests for dashboard + ESPN sync integration.

O sync de resultados ESPN roda de forma SÍNCRONA ao carregar o dashboard (`GET /`),
ANTES de renderizar, para que a classificação já saia atualizada na 1ª carga (sem
F5). Verifica que:
- O dashboard chama o sync síncrono (usuário autenticado), na sessão do request.
- O dashboard renderiza normalmente mesmo se a ESPN/sync falhar (try/except no router).
- Acesso anônimo (redirect para /login) NÃO chama o sync.
- O login NÃO dispara o sync (o gatilho é o dashboard).
- O sync recebe a sessão do request, um datetime e um `deadline` (orçamento de tempo).
- O throttle persistido (`SyncState`) respeita a janela mínima.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        f"sqlite:///{tmp_path / 'dashboard_sync.db'}",
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


def _logar(client: TestClient) -> None:
    """Faz login sem seguir o redirect (não queremos disparar o dashboard ainda)."""
    resp = client.post(
        "/login",
        data={"username": "user1", "senha": "senha123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Gatilho no dashboard
# ---------------------------------------------------------------------------


class TestDashboardComSync:
    def test_dashboard_dispara_sync(self, client: TestClient, db_session: Session) -> None:
        """Carregar o dashboard (autenticado) deve chamar o sync síncrono."""
        _seed_usuario(db_session)
        _logar(client)

        mock_sync = MagicMock(return_value=True)
        with patch("app.routers.dashboard.sincronizar_se_necessario", mock_sync):
            resp = client.get("/")

        assert resp.status_code == 200
        mock_sync.assert_called_once()

    def test_dashboard_ok_mesmo_com_espn_falhando(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Dashboard deve renderizar mesmo que o sync lance exceção.

        A exceção é absorvida pelo try/except do router — nunca deve propagar nem
        quebrar o carregamento da página; cai para os dados já no banco.
        """
        _seed_usuario(db_session)
        _logar(client)

        with patch(
            "app.services.sync_resultados.sincronizar_resultados",
            side_effect=RuntimeError("ESPN caiu"),
        ):
            resp = client.get("/")

        assert resp.status_code == 200

    def test_dashboard_anonimo_nao_dispara_sync(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Acesso anônimo redireciona para /login e NÃO chama o sync."""
        _seed_usuario(db_session)

        mock_sync = MagicMock(return_value=True)
        with patch("app.routers.dashboard.sincronizar_se_necessario", mock_sync):
            resp = client.get("/", follow_redirects=False)

        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"
        mock_sync.assert_not_called()

    def test_dashboard_sync_recebe_sessao_e_deadline(
        self, client: TestClient, db_session: Session
    ) -> None:
        """O sync síncrono recebe a sessão do request, um datetime e um deadline."""
        _seed_usuario(db_session)
        _logar(client)

        captured: list = []

        def _fake_sync(db, agora, deadline=None):
            captured.append((db, agora, deadline))
            return True

        with patch("app.routers.dashboard.sincronizar_se_necessario", _fake_sync):
            resp = client.get("/")

        assert resp.status_code == 200
        assert len(captured) == 1
        db, agora, deadline = captured[0]
        assert isinstance(db, Session)
        assert isinstance(agora, datetime)
        assert isinstance(deadline, float)


class TestLoginNaoDisparaMaisSync:
    def test_login_nao_chama_sync(self, client: TestClient, db_session: Session) -> None:
        """O login não dispara o sync — o gatilho é o dashboard."""
        _seed_usuario(db_session)

        mock_sync = MagicMock(return_value=True)
        with patch("app.routers.dashboard.sincronizar_se_necessario", mock_sync):
            resp = client.post(
                "/login",
                data={"username": "user1", "senha": "senha123"},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Throttle — testado direto em disparar_sync_se_necessario com sessão controlada
# ---------------------------------------------------------------------------


class TestThrottleViaDispararSync:
    def _make_factory(self, db_session: Session):
        def factory():
            return db_session

        return factory

    def test_throttle_dentro_da_janela_nao_chama_sync(self, db_session: Session) -> None:
        """Segunda chamada dentro da janela não deve executar o sync."""
        from app.models.sync_state import SyncState
        from app.services.sync_resultados import CHAVE_SYNC, disparar_sync_se_necessario

        estado = SyncState(chave=CHAVE_SYNC, ultima_execucao=_AGORA)
        db_session.add(estado)
        db_session.commit()

        mock_sync = MagicMock(return_value=ResumoSync())
        factory = self._make_factory(db_session)

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
