"""Tests para o endpoint POST /tarefas/sync (cron externo).

O endpoint dispara o sync de resultados ESPN sem depender de visita ao dashboard,
fechando o buraco em que (Render free hiberna) nada era registrado enquanto ninguém
estava no site. É **aberto** (sem token) de propósito: a ação é inofensiva (só lê
resultados da ESPN, com throttle) e o repositório é público. Verifica:
- POST → 200 {"status": "ok"} e o sync É chamado.
- Funciona sem nenhum header de autenticação.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=True)


class TestTarefasSync:
    def test_dispara_sync_e_responde_ok(self, client: TestClient) -> None:
        mock_sync = MagicMock()
        with patch("app.routers.tarefas.disparar_sync_se_necessario", mock_sync):
            resp = client.post("/tarefas/sync")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        mock_sync.assert_called_once()

    def test_nao_exige_header(self, client: TestClient) -> None:
        """Endpoint aberto: chamar sem cabeçalho algum ainda dispara o sync."""
        mock_sync = MagicMock()
        with patch("app.routers.tarefas.disparar_sync_se_necessario", mock_sync):
            resp = client.post("/tarefas/sync", headers={})

        assert resp.status_code == 200
        mock_sync.assert_called_once()
