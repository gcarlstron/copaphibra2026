"""Tests para o endpoint POST /tarefas/sync (cron externo).

O endpoint dispara o sync de resultados ESPN sem depender de visita ao dashboard,
fechando o buraco em que (Render free hiberna) nada era registrado enquanto ninguém
estava no site. Verifica:
- Token ausente no servidor (SYNC_TOKEN vazio) → 503 (endpoint desabilitado).
- Token recebido errado/ausente → 401, e o sync NÃO é chamado.
- Token correto → 200 {"status": "ok"} e o sync É chamado.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

_TOKEN = "token-secreto-de-teste"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=True)


def _settings(sync_token: str) -> MagicMock:
    s = MagicMock()
    s.sync_token = sync_token
    return s


class TestTarefasSync:
    def test_sem_token_no_servidor_responde_503(self, client: TestClient) -> None:
        mock_sync = MagicMock()
        with patch("app.routers.tarefas.get_settings", return_value=_settings("")), patch(
            "app.routers.tarefas.disparar_sync_se_necessario", mock_sync
        ):
            resp = client.post("/tarefas/sync", headers={"X-Sync-Token": "qualquer"})

        assert resp.status_code == 503
        mock_sync.assert_not_called()

    def test_token_errado_responde_401(self, client: TestClient) -> None:
        mock_sync = MagicMock()
        with patch("app.routers.tarefas.get_settings", return_value=_settings(_TOKEN)), patch(
            "app.routers.tarefas.disparar_sync_se_necessario", mock_sync
        ):
            resp = client.post("/tarefas/sync", headers={"X-Sync-Token": "errado"})

        assert resp.status_code == 401
        mock_sync.assert_not_called()

    def test_token_ausente_responde_401(self, client: TestClient) -> None:
        mock_sync = MagicMock()
        with patch("app.routers.tarefas.get_settings", return_value=_settings(_TOKEN)), patch(
            "app.routers.tarefas.disparar_sync_se_necessario", mock_sync
        ):
            resp = client.post("/tarefas/sync")

        assert resp.status_code == 401
        mock_sync.assert_not_called()

    def test_token_correto_dispara_sync(self, client: TestClient) -> None:
        mock_sync = MagicMock()
        with patch("app.routers.tarefas.get_settings", return_value=_settings(_TOKEN)), patch(
            "app.routers.tarefas.disparar_sync_se_necessario", mock_sync
        ):
            resp = client.post("/tarefas/sync", headers={"X-Sync-Token": _TOKEN})

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        mock_sync.assert_called_once()
