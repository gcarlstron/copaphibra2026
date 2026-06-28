"""Service de sincronização de resultados via ESPN.

Fluxo:
  1. `sincronizar_se_necessario(db, agora, deadline=None)`:
       - Chamado de forma SÍNCRONA ao carregar o dashboard (`GET /`), ANTES de
         renderizar, na própria sessão do request — a classificação/jogos já saem
         atualizados na 1ª carga (sem F5). `deadline` limita o tempo de espera.
       - Lê/cria a linha `SyncState(chave="espn_resultados")`.
       - Throttle DINÂMICO: ~1 min quando há jogo ao vivo/iminente, senão 15 min.
       - Grava `ultima_execucao = agora` ANTES de chamar a ESPN (evita corrida em
         acessos simultâneos no Render free).
       - NÃO captura exceções — o router decide (renderiza com o que há no banco se
         a ESPN falhar).
     `disparar_sync_se_necessario(db_factory, agora)` é o wrapper de
     background/standalone: abre sessão própria, isola erros e fecha a sessão.

  2. `sincronizar_resultados(db, agora, deadline=None)`:
       - PRIMEIRO chama `ingerir_jogos_mata_mata` para criar/atualizar os jogos
         agendados das fases do KO (calendário à frente).
       - Seleciona `Jogo` com `data_hora <= agora` e `status != encerrado`.
       - Agrupa por data (do campo `data_hora`).
       - Para cada data pendente chama `buscar_scoreboard_com_janela` (D-1, D, D+1).
       - FULL_TIME → resolve abrev→nome PT (TeamAlias) → Jogo → `lancar_resultado`
         (pontua). Jogo ao vivo (em andamento/intervalo) → atualiza status/placar
         SEM pontuar.
       - Abreviação sem de-para ou evento sem Jogo: incrementa contador e loga WARNING.
       - `deadline` (segundos de `time.monotonic()`): orçamento total das buscas.
       - Retorna `ResumoSync` com os contadores.

  3. `ingerir_jogos_mata_mata(db, agora, deadline=None)`:
       - Busca a ESPN com range agora.date() até agora.date() + espn_lookahead_dias.
       - Para cada evento com season_slug em FASES_MATA_MATA:
           * get-or-create da Rodada (ordem/nome), criada com aberta=False.
           * get-or-create do Jogo por espn_event_id; se não existir, cria com
             status=agendado. Se existir e não encerrado, atualiza nomes/data_hora
             in-place (resolve placeholder → time real, preservando palpites).
       - Faz commit/flush antes de retornar para que jogos recém-criados com
         data_hora <= agora apareçam na seleção de pendentes do passo seguinte.

Decisão de fuso (2026-06-19):
    O banco armazena horários da planilha (BRT/UTC-3) com label UTC. A ESPN agrupa
    pelo mesmo calendário local, então `date(Jogo.data_hora)` casa diretamente com
    o parâmetro `dates=` da ESPN. O uso de janela D-1/D/D+1 em
    `buscar_scoreboard_com_janela` oferece robustez adicional.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Jogo, Rodada
from app.models.sync_state import SyncState
from app.models.team_alias import TeamAlias
from app.services.admin import lancar_resultado
from app.services.dashboard import (
    STATUS_AGENDADO,
    STATUS_AO_VIVO,
    STATUS_EM_ANDAMENTO,
    STATUS_ENCERRADO,
    STATUS_INTERVALO,
)
from app.services.espn import (
    EspnClientError,
    EventoEspn,
    FASES_MATA_MATA,
    buscar_scoreboard_com_janela,
    buscar_scoreboard_range,
    fase_do_slug,
)

logger = logging.getLogger(__name__)

CHAVE_SYNC = "espn_resultados"

# Janela (horas) após o início em que um jogo ainda pode estar rolando — usada
# para decidir o intervalo de throttle (busca rápida durante jogos ao vivo).
_JANELA_JOGO_AO_VIVO_H = 3

# Após este tempo (horas) do início, um jogo ainda marcado "ao vivo" que a ESPN
# não reporta mais é considerado PRESO e revertido para "agendado" (um jogo dura
# ~2h; 5h é folga suficiente para não pegar um jogo legítimo em andamento).
_LIMITE_AO_VIVO_PRESO_H = 5


@dataclass(slots=True)
class ResumoSync:
    """Resumo do que foi feito em uma execução de sincronização."""

    lancados: int = 0
    atualizados_ao_vivo: int = 0
    revertidos_presos: int = 0
    ignorados_sem_depara: int = 0
    ignorados_sem_jogo: int = 0
    # Contadores do mata-mata (ingerir_jogos_mata_mata — Fase 17)
    rodadas_criadas: int = 0
    jogos_criados: int = 0
    jogos_atualizados_ko: int = 0


# ---------------------------------------------------------------------------
# Ingestão do mata-mata — cria/atualiza jogos agendados via ESPN
# ---------------------------------------------------------------------------


def ingerir_jogos_mata_mata(
    db: Session,
    agora: datetime,
    deadline: float | None = None,
) -> ResumoSync:
    """Cria e/ou atualiza jogos agendados das fases do mata-mata via ESPN.

    Busca um range de datas (agora → agora + espn_lookahead_dias) com uma única
    chamada HTTP. Para cada evento cujo season_slug pertença a FASES_MATA_MATA:

    - get-or-create da Rodada (por ordem), criada com aberta=False.
    - get-or-create do Jogo por espn_event_id:
        * Não existe → cria com status=agendado (pula se data_hora for None).
        * Existe e NÃO encerrado → atualiza nomes e data_hora se mudaram
          (resolução in-place de placeholder para time real, palpites intactos).
        * Existe e ENCERRADO → não mexe (caminho de resultado já encerrou).

    Idempotente: rodar duas vezes não duplica rodadas nem jogos.
    Não reabrir rodada existente (não muda `aberta`).

    Retorna um ResumoSync parcial com os contadores do mata-mata (lancados=0, etc.).
    """
    resumo = ResumoSync()
    settings = get_settings()

    # Verificação de deadline antes de qualquer I/O
    if deadline is not None and time.monotonic() >= deadline:
        logger.warning("Deadline já estourado; ingestão do mata-mata pulada.")
        return resumo

    inicio = agora.date()
    fim = inicio + timedelta(days=settings.espn_lookahead_dias)

    try:
        eventos = buscar_scoreboard_range(inicio, fim, deadline=deadline)
    except EspnClientError as exc:
        logger.warning("ESPN indisponível para range KO %s–%s: %s", inicio, fim, exc)
        return resumo
    except Exception:
        logger.warning(
            "Erro inesperado ao buscar ESPN range KO %s–%s", inicio, fim, exc_info=True
        )
        return resumo

    if not eventos:
        return resumo

    # Carrega de-para abreviacao → nome PT (para times reais do R32)
    depara_stmt = select(TeamAlias.abreviacao, TeamAlias.nome)
    depara: dict[str, str] = {r.abreviacao: r.nome for r in db.execute(depara_stmt).all()}

    # Cache de rodadas por ordem (evita SELECT repetido por evento)
    rodadas_cache: dict[int, Rodada] = {}

    for ev in eventos:
        fase = fase_do_slug(ev.season_slug)
        if fase is None:
            continue  # slug não é mata-mata (ex.: "group-stage")

        ordem, nome_rodada = fase

        # get-or-create da Rodada
        if ordem not in rodadas_cache:
            rodada = db.scalar(select(Rodada).where(Rodada.ordem == ordem))
            if rodada is None:
                rodada = Rodada(nome=nome_rodada, ordem=ordem, aberta=False)
                db.add(rodada)
                db.flush()
                resumo.rodadas_criadas += 1
                logger.info("Rodada KO criada: ordem=%d nome=%r", ordem, nome_rodada)
            rodadas_cache[ordem] = rodada

        rodada = rodadas_cache[ordem]

        if not ev.event_id:
            logger.warning("Evento ESPN sem event_id; ignorando.")
            continue

        # Resolve nomes: times reais → de-para PT; placeholders → displayName da ESPN
        nome_casa = depara.get(ev.abrev_casa) or ev.nome_casa_espn or ev.abrev_casa
        nome_visitante = depara.get(ev.abrev_visitante) or ev.nome_visitante_espn or ev.abrev_visitante

        # get-or-create do Jogo por espn_event_id
        jogo = db.scalar(select(Jogo).where(Jogo.espn_event_id == ev.event_id))

        if jogo is None:
            # Criar novo jogo — pula se sem data_hora (não sabemos quando jogar)
            if ev.data_hora is None:
                logger.warning(
                    "Evento ESPN %r sem data_hora; jogo não criado.", ev.event_id
                )
                continue
            try:
                jogo = Jogo(
                    rodada_id=rodada.id,
                    espn_event_id=ev.event_id,
                    data_hora=ev.data_hora,
                    time_casa=nome_casa,
                    time_visitante=nome_visitante,
                    status=STATUS_AGENDADO,
                )
                db.add(jogo)
                db.flush()
                resumo.jogos_criados += 1
                logger.info(
                    "Jogo KO criado: event_id=%r %r vs %r data=%s",
                    ev.event_id,
                    nome_casa,
                    nome_visitante,
                    ev.data_hora,
                )
            except IntegrityError:
                # UniqueConstraint (rodada_id, time_casa, time_visitante) violada
                # — pode ocorrer se dois eventos de KO ainda tiverem o mesmo
                # placeholder de times. Rollback seguro: pula este jogo.
                db.rollback()
                logger.warning(
                    "IntegrityError ao criar jogo KO event_id=%r; pulando.",
                    ev.event_id,
                )
        else:
            # Jogo já existe — só atualiza se NÃO encerrado e houve mudança
            if jogo.status == STATUS_ENCERRADO:
                continue

            mudou = False
            if jogo.time_casa != nome_casa:
                jogo.time_casa = nome_casa
                mudou = True
            if jogo.time_visitante != nome_visitante:
                jogo.time_visitante = nome_visitante
                mudou = True
            # Normaliza naive→aware antes de comparar: o SQLite devolve data_hora
            # naive (sem tz), enquanto ev.data_hora é aware (em_fuso_dos_dados).
            # Sem isso, naive != aware é sempre True → update espúrio a cada sync.
            data_hora_atual = jogo.data_hora
            if data_hora_atual is not None and data_hora_atual.tzinfo is None:
                data_hora_atual = data_hora_atual.replace(tzinfo=timezone.utc)
            if ev.data_hora is not None and data_hora_atual != ev.data_hora:
                jogo.data_hora = ev.data_hora
                mudou = True

            if mudou:
                resumo.jogos_atualizados_ko += 1
                logger.info(
                    "Jogo KO atualizado in-place: event_id=%r %r vs %r",
                    ev.event_id,
                    nome_casa,
                    nome_visitante,
                )

    # Commit antes de retornar para que jogos recém-criados com
    # data_hora <= agora apareçam na seleção de pendentes do sync de resultados.
    db.commit()

    if resumo.rodadas_criadas or resumo.jogos_criados or resumo.jogos_atualizados_ko:
        logger.info(
            "Ingestão KO: %d rodadas criadas, %d jogos criados, %d jogos atualizados.",
            resumo.rodadas_criadas,
            resumo.jogos_criados,
            resumo.jogos_atualizados_ko,
        )

    return resumo


# ---------------------------------------------------------------------------
# Sincronização principal
# ---------------------------------------------------------------------------


def sincronizar_resultados(
    db: Session,
    agora: datetime,
    deadline: float | None = None,
) -> ResumoSync:
    """Busca resultados na ESPN e lança os que ainda não estão encerrados no banco.

    Idempotente: jogos já encerrados são ignorados.

    `deadline` (opcional, em segundos de `time.monotonic()`): orçamento total de
    tempo para as buscas na ESPN. Usado no caminho síncrono do dashboard. Ao
    estourar, as datas ainda não consultadas são puladas (resumo parcial) e a
    página renderiza com o que já estiver no banco.
    """
    resumo = ResumoSync()

    # 0. Ingestão do mata-mata — cria/atualiza jogos agendados das fases KO.
    #    Faz commit internamente; os jogos recém-criados com data_hora <= agora
    #    aparecem na seleção de pendentes do passo seguinte.
    resumo_ko = ingerir_jogos_mata_mata(db, agora, deadline=deadline)
    resumo.rodadas_criadas = resumo_ko.rodadas_criadas
    resumo.jogos_criados = resumo_ko.jogos_criados
    resumo.jogos_atualizados_ko = resumo_ko.jogos_atualizados_ko

    # 1. Seleciona jogos pendentes (antes de agora, não encerrados)
    stmt = select(
        Jogo.id,
        Jogo.data_hora,
        Jogo.time_casa,
        Jogo.time_visitante,
        Jogo.status,
    ).where(
        Jogo.data_hora <= agora,
        Jogo.status != STATUS_ENCERRADO,
    )
    jogos_pendentes = db.execute(stmt).all()

    if not jogos_pendentes:
        return resumo

    # 2. Carrega o de-para de abreviação → nome PT-BR em memória
    depara_stmt = select(TeamAlias.abreviacao, TeamAlias.nome)
    depara_rows = db.execute(depara_stmt).all()
    depara: dict[str, str] = {r.abreviacao: r.nome for r in depara_rows}

    # 3. Agrupa jogos pendentes por data (campo data_hora, usando só a parte date)
    jogos_por_data: dict[date, list] = defaultdict(list)
    for jogo in jogos_pendentes:
        d = jogo.data_hora.date() if hasattr(jogo.data_hora, "date") else jogo.data_hora
        jogos_por_data[d].append(jogo)

    # 4. Para cada data, busca a ESPN UMA única vez e materializa os eventos.
    #    A estrutura é reutilizada tanto para lançar resultados quanto para
    #    contar ignorados_sem_jogo — eliminando a segunda rodada de fetch.
    #    O `deadline` (caminho síncrono) limita o tempo total de espera.
    eventos_por_data: dict[date, list] = {}
    for data_alvo in jogos_por_data:
        if deadline is not None and time.monotonic() >= deadline:
            logger.warning(
                "Deadline do sync atingido; data %s não consultada na ESPN.", data_alvo
            )
            eventos_por_data[data_alvo] = []
            continue
        try:
            eventos_por_data[data_alvo] = buscar_scoreboard_com_janela(
                data_alvo, deadline=deadline
            )
        except EspnClientError as exc:
            logger.warning("ESPN indisponível para %s: %s", data_alvo, exc)
            eventos_por_data[data_alvo] = []
        except Exception:
            logger.warning(
                "Erro inesperado ao buscar ESPN para %s", data_alvo, exc_info=True
            )
            eventos_por_data[data_alvo] = []

    # 5. Para cada data, monta o índice de encerrados e cruza com jogos pendentes.
    #    Cada data é buscada exatamente uma vez (ver passo 4 acima).
    for data_alvo, jogos_do_dia in jogos_por_data.items():
        if deadline is not None and time.monotonic() >= deadline:
            logger.warning(
                "Deadline do sync atingido na fase de escrita; resultados parciais."
            )
            break
        eventos = eventos_por_data[data_alvo]

        # Monta índice de eventos encerrados por (nome_casa, nome_visitante)
        eventos_encerrados: dict[tuple[str, str], tuple[int, int]] = {}
        for ev in eventos:
            if not ev.encerrado:
                continue

            nome_casa = depara.get(ev.abrev_casa)
            nome_visitante = depara.get(ev.abrev_visitante)

            if nome_casa is None:
                logger.warning(
                    "Abreviação ESPN '%s' sem de-para; ignorando evento.", ev.abrev_casa
                )
                resumo.ignorados_sem_depara += 1
                continue
            if nome_visitante is None:
                logger.warning(
                    "Abreviação ESPN '%s' sem de-para; ignorando evento.",
                    ev.abrev_visitante,
                )
                resumo.ignorados_sem_depara += 1
                continue

            if ev.gols_casa is None or ev.gols_visitante is None:
                logger.warning(
                    "Evento %s vs %s encerrado mas sem placar; ignorando.",
                    ev.abrev_casa,
                    ev.abrev_visitante,
                )
                continue

            eventos_encerrados[(nome_casa, nome_visitante)] = (
                ev.gols_casa,
                ev.gols_visitante,
            )

        # Cruza com os jogos pendentes do dia
        for jogo in jogos_do_dia:
            chave = (jogo.time_casa, jogo.time_visitante)
            if chave not in eventos_encerrados:
                # Evento não encontrado na ESPN (pode estar em outra data da janela
                # ou simplesmente não encerrado ainda)
                continue

            gols_c, gols_v = eventos_encerrados[chave]

            # Verifica novamente no banco se ainda não foi encerrado (idempotência)
            jogo_atual = db.get(Jogo, jogo.id)
            if jogo_atual is None or jogo_atual.status == STATUS_ENCERRADO:
                continue

            try:
                lancar_resultado(db, jogo.id, gols_c, gols_v)
                resumo.lancados += 1
                logger.info(
                    "Resultado lançado: %s %d×%d %s (jogo_id=%d)",
                    jogo.time_casa,
                    gols_c,
                    gols_v,
                    jogo.time_visitante,
                    jogo.id,
                )
            except Exception:
                logger.warning(
                    "Falha ao lançar resultado jogo_id=%d", jogo.id, exc_info=True
                )

    # 5b. Atualiza status/placar de jogos AO VIVO (em andamento / intervalo).
    #     NÃO pontua — só lancar_resultado (FULL_TIME) recalcula Palpite.pontos.
    #     Reutiliza os eventos já materializados no passo 4.
    ao_vivo_atualizados: set[int] = set()
    for data_alvo, jogos_do_dia in jogos_por_data.items():
        if deadline is not None and time.monotonic() >= deadline:
            logger.warning(
                "Deadline do sync atingido na atualização ao vivo; parcial."
            )
            break
        ao_vivo_idx: dict[tuple[str, str], EventoEspn] = {}
        for ev in eventos_por_data[data_alvo]:
            if not ev.ao_vivo:
                continue
            nome_casa = depara.get(ev.abrev_casa)
            nome_visitante = depara.get(ev.abrev_visitante)
            if nome_casa is None or nome_visitante is None:
                continue
            ao_vivo_idx[(nome_casa, nome_visitante)] = ev

        for jogo in jogos_do_dia:
            ev = ao_vivo_idx.get((jogo.time_casa, jogo.time_visitante))
            if ev is None:
                continue

            jogo_atual = db.get(Jogo, jogo.id)
            if jogo_atual is None or jogo_atual.status == STATUS_ENCERRADO:
                continue

            novo_status = STATUS_INTERVALO if ev.no_intervalo else STATUS_EM_ANDAMENTO
            # Não sobrescrever um placar já conhecido com None: a ESPN às vezes
            # reporta o evento ao vivo sem os gols. Mantém o último placar bom.
            novo_gols_casa = ev.gols_casa if ev.gols_casa is not None else jogo_atual.gols_casa
            novo_gols_visitante = (
                ev.gols_visitante if ev.gols_visitante is not None else jogo_atual.gols_visitante
            )
            mudou = (
                jogo_atual.status != novo_status
                or jogo_atual.gols_casa != novo_gols_casa
                or jogo_atual.gols_visitante != novo_gols_visitante
            )
            if not mudou:
                continue

            jogo_atual.status = novo_status
            jogo_atual.gols_casa = novo_gols_casa
            jogo_atual.gols_visitante = novo_gols_visitante
            resumo.atualizados_ao_vivo += 1
            ao_vivo_atualizados.add(jogo.id)
            logger.info(
                "Jogo ao vivo atualizado: %s %s×%s %s (status=%s, jogo_id=%d)",
                jogo.time_casa,
                novo_gols_casa,
                novo_gols_visitante,
                jogo.time_visitante,
                novo_status,
                jogo.id,
            )

    # 5c. Reverte jogos "presos" ao vivo: marcados em andamento/intervalo há mais
    #     de _LIMITE_AO_VIVO_PRESO_H horas e que a ESPN NÃO reportou ao vivo nesta
    #     execução (parou de cobri-los). Volta para "agendado" sem placar, para não
    #     ficarem eternamente "ao vivo" no dashboard; a próxima sync tenta resolver
    #     o resultado de novo (segue pendente). Não toca nos que a ESPN ainda
    #     reporta ao vivo agora (ficaram em ao_vivo_atualizados).
    limite_preso = agora - timedelta(hours=_LIMITE_AO_VIVO_PRESO_H)
    presos = db.scalars(
        select(Jogo).where(
            Jogo.status.in_(STATUS_AO_VIVO),
            Jogo.data_hora <= limite_preso,
        )
    ).all()
    for jogo_preso in presos:
        if jogo_preso.id in ao_vivo_atualizados:
            continue
        jogo_preso.status = STATUS_AGENDADO
        jogo_preso.gols_casa = None
        jogo_preso.gols_visitante = None
        resumo.revertidos_presos += 1
        logger.warning(
            "Jogo ao vivo preso revertido para 'agendado': jogo_id=%d", jogo_preso.id
        )

    db.commit()

    # 6. Conta ignorados_sem_jogo reutilizando os eventos já materializados.
    #    Constrói o conjunto completo de pares pendentes para O(1) lookup.
    pares_pendentes: set[tuple[str, str]] = {
        (j.time_casa, j.time_visitante)
        for jgs in jogos_por_data.values()
        for j in jgs
    }
    for data_alvo, eventos in eventos_por_data.items():
        for ev in eventos:
            if not ev.encerrado:
                continue

            nome_casa = depara.get(ev.abrev_casa)
            nome_visitante = depara.get(ev.abrev_visitante)
            if nome_casa is None or nome_visitante is None:
                continue  # já contado em ignorados_sem_depara

            if (nome_casa, nome_visitante) not in pares_pendentes:
                logger.warning(
                    "Evento ESPN %s vs %s encerrado mas não há Jogo pendente correspondente.",
                    nome_casa,
                    nome_visitante,
                )
                resumo.ignorados_sem_jogo += 1

    return resumo


# ---------------------------------------------------------------------------
# Throttle + disparo
# ---------------------------------------------------------------------------


def _get_or_create_sync_state(db: Session, chave: str) -> SyncState:
    """Retorna a linha de SyncState, criando-a se não existir."""
    estado = db.scalar(select(SyncState).where(SyncState.chave == chave))
    if estado is None:
        estado = SyncState(chave=chave, ultima_execucao=None)
        db.add(estado)
        db.commit()
        db.refresh(estado)
    return estado


def _reivindicar_slot(
    db: Session, valor_lido: datetime | None, agora_utc: datetime
) -> bool:
    """Compare-and-set atômico de ``SyncState.ultima_execucao``.

    Avança ``ultima_execucao`` para ``agora_utc`` somente se a coluna ainda for
    ``valor_lido`` (o valor lido antes). Como é um único ``UPDATE ... WHERE`` (o
    banco serializa updates concorrentes na mesma linha), apenas UMA requisição
    "ganha" o slot — as demais recebem ``rowcount == 0``. Evita fetches
    duplicados à ESPN quando várias abas disparam o sync quase ao mesmo tempo
    (auto-refresh durante jogo ao vivo). Retorna True se reivindicou o slot.
    """
    if valor_lido is None:
        condicao = SyncState.ultima_execucao.is_(None)
    else:
        condicao = SyncState.ultima_execucao == valor_lido
    resultado = db.execute(
        update(SyncState)
        .where(SyncState.chave == CHAVE_SYNC, condicao)
        .values(ultima_execucao=agora_utc)
    )
    db.commit()
    return resultado.rowcount == 1


def _ha_jogo_ao_vivo_ou_iminente(db: Session, agora: datetime) -> bool:
    """True se há jogo ao vivo (em andamento/intervalo) ou agendado já iniciado há pouco.

    Cobre tanto um jogo já marcado ao vivo quanto um recém-iniciado que ainda não
    foi detectado. A janela de `_JANELA_JOGO_AO_VIVO_H` horas evita fast-polling
    eterno de um jogo que começou mas nunca recebeu resultado.
    """
    agora_utc = agora if agora.tzinfo is not None else agora.replace(tzinfo=timezone.utc)
    limite_inicio = agora_utc - timedelta(hours=_JANELA_JOGO_AO_VIVO_H)

    stmt = (
        select(Jogo.id)
        .where(
            Jogo.status != STATUS_ENCERRADO,
            Jogo.data_hora <= agora_utc,
            Jogo.data_hora >= limite_inicio,
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def _intervalo_efetivo_min(db: Session, agora: datetime, settings) -> int:
    """Intervalo de throttle em minutos — curto quando há jogo ao vivo/iminente."""
    if _ha_jogo_ao_vivo_ou_iminente(db, agora):
        return settings.espn_sync_intervalo_ao_vivo_min
    return settings.espn_sync_intervalo_min


def sincronizar_se_necessario(
    db: Session,
    agora: datetime,
    deadline: float | None = None,
) -> bool:
    """Executa o sync respeitando o throttle, usando a sessão fornecida.

    Usado no caminho SÍNCRONO do dashboard (`GET /`): roda ANTES de renderizar,
    na própria sessão do request, para que `montar_dashboard` já enxergue os
    resultados/jogos ao vivo recém-atualizados.

    - Throttle DINÂMICO via `_intervalo_efetivo_min` (~1 min com jogo ao vivo).
    - Grava `ultima_execucao = agora` ANTES de chamar a ESPN (evita corrida).
    - `deadline` (segundos de `time.monotonic()`): orçamento total repassado à
      busca na ESPN, para a página não travar se a ESPN estiver lenta/fora.

    Retorna `True` se o sync rodou (janela aberta), `False` se foi throttled.
    NÃO captura exceções — o caller (router) decide como tratar; assim a página
    pode renderizar com os dados existentes se a ESPN falhar.
    """
    settings = get_settings()
    # Intervalo dinâmico: ~1 min enquanto há jogo ao vivo; 15 min caso contrário.
    intervalo_min = _intervalo_efetivo_min(db, agora, settings)
    agora_utc = agora if agora.tzinfo is not None else agora.replace(tzinfo=timezone.utc)

    estado = _get_or_create_sync_state(db, CHAVE_SYNC)

    # Throttle: respeita a janela mínima (decisão em Python, robusta a tz/naive).
    if estado.ultima_execucao is not None:
        ultima = estado.ultima_execucao
        # Normaliza para UTC se tiver tzinfo
        if ultima.tzinfo is None:
            ultima = ultima.replace(tzinfo=timezone.utc)
        diferenca = agora_utc - ultima
        # Só faz throttle dentro da janela "para frente". Diferença negativa
        # (ex.: ultima_execucao gravada na convenção de fuso antiga logo após o
        # deploy do ADR-002, ou skew de relógio) → executa, em vez de ficar preso
        # achando que rodou "no futuro".
        if timedelta(0) <= diferenca < timedelta(minutes=intervalo_min):
            logger.debug(
                "Sync ESPN throttled: última execução há %.1f min (intervalo=%d min).",
                diferenca.total_seconds() / 60,
                intervalo_min,
            )
            return False

    # Reivindica o slot ANTES de chamar a ESPN, de forma atômica (compare-and-set):
    # grava ultima_execucao só se ela ainda for o valor lido acima. Em acessos
    # simultâneos (várias abas no auto-refresh durante um jogo ao vivo), só UMA
    # requisição vence — as demais saem aqui, evitando fetches duplicados.
    if not _reivindicar_slot(db, estado.ultima_execucao, agora_utc):
        logger.debug("Sync ESPN: slot já reivindicado por outra requisição; pulando.")
        return False

    logger.info("Iniciando sincronização de resultados ESPN.")
    resumo = sincronizar_resultados(db, agora_utc, deadline=deadline)
    logger.info(
        "Sync ESPN concluído: %d lançados, %d ao vivo, %d revertidos, "
        "%d sem de-para, %d sem jogo | KO: %d rodadas, %d jogos criados, %d atualizados.",
        resumo.lancados,
        resumo.atualizados_ao_vivo,
        resumo.revertidos_presos,
        resumo.ignorados_sem_depara,
        resumo.ignorados_sem_jogo,
        resumo.rodadas_criadas,
        resumo.jogos_criados,
        resumo.jogos_atualizados_ko,
    )
    return True


def disparar_sync_se_necessario(
    db_factory: Callable[[], Session],
    agora: datetime,
) -> None:
    """Wrapper de background/standalone: abre sessão própria e isola erros.

    Mantido para usos fora do request (ex.: tarefa agendada/CLI). Diferente do
    caminho síncrono do dashboard:
    - Abre uma sessão própria via `db_factory` e a fecha ao final.
    - Envolve TUDO em try/except amplo — nunca propaga exceção.
    - Sem `deadline` (orçamento ilimitado), pois não bloqueia nenhuma resposta.
    """
    db = db_factory()
    try:
        sincronizar_se_necessario(db, agora)
    except Exception:
        logger.exception("Erro inesperado no sync ESPN; ignorando para não afetar o caller.")
    finally:
        db.close()
