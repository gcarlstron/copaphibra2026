"""Endpoint operacional de sync, acionado por agendador externo (cron).

`POST /tarefas/sync` dispara a sincronização de resultados da ESPN SEM depender de
uma visita humana ao dashboard — fechando o buraco em que, no Render free, o app
hiberna e nenhum jogo é registrado enquanto ninguém está no site.

Diferenças para o caminho do dashboard (`GET /`):
  - Roda via `disparar_sync_se_necessario`, que abre sessão própria, isola erros e
    **não passa deadline** (orçamento ilimitado) — então sempre completa a busca e o
    registro, ao contrário do caminho síncrono da página (limitado para não travar).
  - **Aberto** (sem token): a ação é inofensiva — só dispara a leitura de resultados
    da ESPN, com throttle. Não injeta, altera nem apaga dados. Mantido simples de
    propósito para um bolão interno; o repositório é público, então um token só
    protegeria se fosse um Secret de verdade — não vale a complexidade aqui.

O throttle persistido (`SyncState`) garante que bater com frequência é barato: só a
1ª chamada de cada janela realmente busca na ESPN; as demais saem no throttle.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.database import SessionLocal
from app.services.sync_resultados import disparar_sync_se_necessario
from app.services.tempo import agora as agora_dados

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tarefas", tags=["tarefas"])


@router.post("/sync")
def disparar_sync() -> dict[str, str]:
    """Dispara o sync de resultados ESPN (acionado por cron externo).

    Síncrono, em sessão própria; `disparar_sync_se_necessario` respeita o throttle e
    isola erros internamente (nunca propaga). Retorna 200 `{"status": "ok"}` quando o
    disparo foi aceito — o sync em si pode ter sido throttled ou ter falhado em
    silêncio (ver logs do servidor).
    """
    disparar_sync_se_necessario(SessionLocal, agora_dados())
    return {"status": "ok"}
