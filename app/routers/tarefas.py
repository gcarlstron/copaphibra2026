"""Endpoint operacional de sync, acionado por agendador externo (cron).

`POST /tarefas/sync` dispara a sincronização de resultados da ESPN SEM depender de
uma visita humana ao dashboard — fechando o buraco em que, no Render free, o app
hiberna e nenhum jogo é registrado enquanto ninguém está no site.

Diferenças para o caminho do dashboard (`GET /`):
  - Roda via `disparar_sync_se_necessario`, que abre sessão própria, isola erros e
    **não passa deadline** (orçamento ilimitado) — então sempre completa a busca e o
    registro, ao contrário do caminho síncrono da página (limitado para não travar).
  - Protegido por token (`SYNC_TOKEN`), comparado em tempo constante. Sem token
    configurado, o endpoint responde 503 (nunca fica aberto).

O throttle persistido (`SyncState`) garante que bater com frequência é barato: só a
1ª chamada de cada janela realmente busca na ESPN; as demais saem no throttle.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, status

from app.config import get_settings
from app.database import SessionLocal
from app.services.sync_resultados import disparar_sync_se_necessario
from app.services.tempo import agora as agora_dados

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tarefas", tags=["tarefas"])


def _verificar_token(token_recebido: str | None) -> None:
    """Valida o token do header `X-Sync-Token` em tempo constante.

    503 se o token não estiver configurado no servidor (endpoint desabilitado);
    401 se o token recebido for ausente ou diferente.
    """
    esperado = get_settings().sync_token
    if not esperado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Endpoint de sync desabilitado: defina a variável SYNC_TOKEN.",
        )
    if not token_recebido or not secrets.compare_digest(token_recebido, esperado):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        )


@router.post("/sync")
def disparar_sync(x_sync_token: str | None = Header(default=None)) -> dict[str, str]:
    """Dispara o sync de resultados ESPN (acionado por cron externo).

    Síncrono, em sessão própria; `disparar_sync_se_necessario` respeita o throttle e
    isola erros internamente (nunca propaga). Retorna 200 `{"status": "ok"}` quando o
    disparo foi aceito — o sync em si pode ter sido throttled ou ter falhado em
    silêncio (ver logs do servidor).
    """
    _verificar_token(x_sync_token)
    disparar_sync_se_necessario(SessionLocal, agora_dados())
    return {"status": "ok"}
