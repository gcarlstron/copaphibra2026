"""Cliente ESPN — busca resultados da fase de grupos e do mata-mata do Mundial 2026.

Endpoint público (sem auth):
  https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=AAAAMMDD
  https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=AAAAMMDD-BBBBMMDD

Decisão de fuso (confirmada empiricamente em 2026-06-19):
    A ESPN agrupa jogos pelo mesmo calendário local (BRT/UTC-3) que consta na
    planilha importada.  O campo `data_hora` no banco foi gravado com os horários
    da planilha (BRT), portanto a data local de `Jogo.data_hora` bate diretamente
    com o parâmetro `dates=` da ESPN.
    Exemplo verificado:
      - MEX vs RSA: DB=2026-06-11 16:00 "UTC" (=13:00 BRT na realidade),
        ESPN key=20260611.
      - KOR vs CZE: DB=2026-06-11 23:00 "UTC" (=20:00 BRT), ESPN key=20260611.
    Para robustez contra eventuais inconsistências, o service de sync consulta
    D-1, D e D+1 para cada data pendente e une todos os resultados.

Tratamento de erro em `buscar_scoreboard` e `buscar_scoreboard_range`:
    Em caso de erro de rede, timeout ou status HTTP não-2xx, a função levanta
    `EspnClientError`. O service de sync captura essa exceção e incrementa o
    contador de ignorados, sem derrubar o sync nem o login.

Mata-mata — slugs de fase (campo `event.season.slug`, confirmado ao vivo):
    "round-of-32"     → 16-avos de final  (ordem 4)
    "round-of-16"     → Oitavas de final  (ordem 5)
    "quarterfinals"   → Quartas de final  (ordem 6)
    "semifinals"      → Semifinais        (ordem 7)
    "3rd-place-match" → Disputa de 3º lugar (ordem 8)
    "final"           → Final             (ordem 9)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx2 as httpx

from app.config import get_settings
from app.services import tempo

logger = logging.getLogger(__name__)

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
)
ESPN_STATUS_FULL_TIME = "STATUS_FULL_TIME"
ESPN_STATUS_SCHEDULED = "STATUS_SCHEDULED"
ESPN_STATUS_HALFTIME = "STATUS_HALFTIME"

# `status.type.state` da ESPN: "pre" (agendado), "in" (em andamento), "post" (fim).
ESPN_STATE_PRE = "pre"
ESPN_STATE_IN = "in"
ESPN_STATE_POST = "post"

# Mapa slug → (ordem_da_rodada, nome_PT) para as fases do mata-mata.
# As ordens 1–3 são reservadas para as 3 rodadas da fase de grupos.
FASES_MATA_MATA: dict[str, tuple[int, str]] = {
    "round-of-32": (4, "16-avos de final"),
    "round-of-16": (5, "Oitavas de final"),
    "quarterfinals": (6, "Quartas de final"),
    "semifinals": (7, "Semifinais"),
    "3rd-place-match": (8, "Disputa de 3º lugar"),
    "final": (9, "Final"),
}


def fase_do_slug(slug: str) -> tuple[int, str] | None:
    """Retorna (ordem, nome_PT) para um slug de fase do mata-mata, ou None."""
    return FASES_MATA_MATA.get(slug)


class EspnClientError(RuntimeError):
    """Raised when the ESPN API returns an error or times out."""


@dataclass(slots=True)
class EventoEspn:
    """Dados de um evento (jogo) retornado pela ESPN."""

    abrev_casa: str
    abrev_visitante: str
    gols_casa: int | None
    gols_visitante: int | None
    status: str
    encerrado: bool
    estado: str = ""  # status.type.state: "pre" | "in" | "post" (default "" = ausente)

    # Campos adicionados para o mata-mata (Fase 17).
    # Defaults preservam compatibilidade: testes existentes instanciam EventoEspn
    # com apenas os campos obrigatórios acima.
    event_id: str = ""  # event.id (string numérica estável, ex.: "760486")
    season_slug: str = ""  # event.season.slug (ex.: "round-of-32")
    data_hora: datetime | None = None  # event.date → convertido p/ fuso dos dados
    nome_casa_espn: str = ""  # team.displayName or name do lado home
    nome_visitante_espn: str = ""  # team.displayName or name do lado away

    @property
    def ao_vivo(self) -> bool:
        """True se o jogo está em andamento (inclui o intervalo)."""
        if self.encerrado:
            return False
        if self.estado:
            return self.estado == ESPN_STATE_IN
        # Fallback quando a ESPN não envia `state`: qualquer status que não seja
        # agendado/vazio é tratado como ao vivo.
        return self.status not in ("", ESPN_STATUS_SCHEDULED)

    @property
    def no_intervalo(self) -> bool:
        """True se o jogo está no intervalo."""
        return self.ao_vivo and self.status == ESPN_STATUS_HALFTIME


# ---------------------------------------------------------------------------
# Parser puro — sem I/O, sem estado externo
# ---------------------------------------------------------------------------


def _parse_score(raw: object) -> int | None:
    """Converte o placar bruto da ESPN (string ou None) em int, ou None."""
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_event_date(date_str: object) -> datetime | None:
    """Converte o campo `date` do evento ESPN (ISO 8601 / "Z") p/ fuso dos dados.

    Aceita formatos como "2026-06-28T19:00Z" ou "2026-06-28T19:00:00+00:00".
    Retorna None se o campo for ausente, inválido ou None.

    O retorno está no fuso dos dados (BRT-rotulado-UTC), casando com a convenção
    usada pelo banco (ADR-002) e pela fase de grupos importada da planilha.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        # Normaliza "Z" para "+00:00" (Python 3.10 e anterior não suportam "Z")
        iso = date_str.replace("Z", "+00:00")
        aware = datetime.fromisoformat(iso)
        return tempo.em_fuso_dos_dados(aware)
    except (ValueError, TypeError):
        logger.debug("Não foi possível parsear data ESPN: %r", date_str)
        return None


def parse_eventos(payload: dict) -> list[EventoEspn]:
    """Converte o payload bruto da ESPN em lista de EventoEspn.

    Defensivo: campos faltando não levantam exceção — o evento é silenciosamente
    descartado com um log WARNING.

    Para o mata-mata (Fase 17), popula os campos extras: event_id, season_slug,
    data_hora (convertida para fuso dos dados), nome_casa_espn, nome_visitante_espn.
    Esses campos têm defaults, portanto testes que instanciam EventoEspn diretamente
    (sem esses campos) continuam funcionando sem modificação.
    """
    eventos: list[EventoEspn] = []

    for event in (payload.get("events") or []):
        try:
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]

            status_type = comp.get("status", {}).get("type", {})
            status_name: str = status_type.get("name", "") or ""
            estado: str = status_type.get("state", "") or ""
            # `completed` é o sinal canônico de "o jogo terminou": cobre FULL_TIME e
            # também os finais do mata-mata — prorrogação (STATUS_FINAL_AET) e
            # pênaltis (STATUS_FINAL_PEN) — que a fase de grupos nunca via. Sem isso,
            # um jogo decidido nos pênaltis ficava preso como "agendado". Fallback por
            # nome para payloads sem o campo (testes/legados). O placar do competidor é
            # o do tempo normal/prorrogação; os pênaltis vêm em `shootoutScore` à parte
            # e NÃO entram na pontuação (o bolão pontua o placar — 1×1 = empate).
            encerrado = bool(status_type.get("completed")) or status_name == ESPN_STATUS_FULL_TIME

            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            # Resolve home/away
            home = next(
                (c for c in competitors if c.get("homeAway") == "home"), None
            )
            away = next(
                (c for c in competitors if c.get("homeAway") == "away"), None
            )
            if home is None or away is None:
                continue

            abrev_casa = (home.get("team") or {}).get("abbreviation") or ""
            abrev_visitante = (away.get("team") or {}).get("abbreviation") or ""
            if not abrev_casa or not abrev_visitante:
                continue

            # Scores are strings or None
            gols_casa = _parse_score(home.get("score"))
            gols_visitante = _parse_score(away.get("score"))

            # Campos do mata-mata — populados para todos os eventos; ficam nos
            # defaults ("" / None) para eventos sem esses campos.
            event_id: str = str(event.get("id") or "")
            season_info = event.get("season") or {}
            season_slug: str = str(season_info.get("slug") or "")
            data_hora_ev = _parse_event_date(event.get("date"))

            home_team = home.get("team") or {}
            away_team = away.get("team") or {}
            nome_casa_espn: str = str(
                home_team.get("displayName") or home_team.get("name") or ""
            )
            nome_visitante_espn: str = str(
                away_team.get("displayName") or away_team.get("name") or ""
            )

            eventos.append(
                EventoEspn(
                    abrev_casa=abrev_casa,
                    abrev_visitante=abrev_visitante,
                    gols_casa=gols_casa,
                    gols_visitante=gols_visitante,
                    status=status_name,
                    encerrado=encerrado,
                    estado=estado,
                    event_id=event_id,
                    season_slug=season_slug,
                    data_hora=data_hora_ev,
                    nome_casa_espn=nome_casa_espn,
                    nome_visitante_espn=nome_visitante_espn,
                )
            )
        except Exception:
            logger.warning("Evento ESPN malformado; ignorando.", exc_info=True)

    return eventos


# ---------------------------------------------------------------------------
# HTTP — dependência de I/O isolada aqui
# ---------------------------------------------------------------------------


def buscar_scoreboard(
    data: date,
    timeout_s: float | None = None,
    _transport: httpx.BaseTransport | None = None,
) -> list[EventoEspn]:
    """Busca os eventos do scoreboard ESPN para uma data específica.

    `_transport` é um parâmetro de injeção usado nos testes para evitar I/O real
    (passe `httpx2.MockTransport`).

    Em caso de erro de rede, timeout ou HTTP não-2xx, levanta `EspnClientError`.
    O caller (sync service) captura e trata — nunca propaga até o login.
    """
    if timeout_s is None:
        settings = get_settings()
        timeout_s = settings.espn_timeout_s

    date_str = data.strftime("%Y%m%d")
    url = f"{ESPN_SCOREBOARD_URL}?dates={date_str}"

    client_kwargs: dict = {
        "timeout": httpx.Timeout(timeout_s),
    }
    if _transport is not None:
        client_kwargs["transport"] = _transport

    try:
        with httpx.Client(**client_kwargs) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise EspnClientError(f"Timeout ao buscar ESPN para {date_str}") from exc
    except httpx.HTTPStatusError as exc:
        raise EspnClientError(
            f"ESPN retornou HTTP {exc.response.status_code} para {date_str}"
        ) from exc
    except httpx.RequestError as exc:
        raise EspnClientError(f"Erro de rede ao buscar ESPN para {date_str}") from exc

    return parse_eventos(payload)


def buscar_scoreboard_range(
    data_inicio: date,
    data_fim: date,
    timeout_s: float | None = None,
    deadline: float | None = None,
    _transport: httpx.BaseTransport | None = None,
) -> list[EventoEspn]:
    """Busca todos os eventos ESPN em um intervalo de datas (uma única chamada HTTP).

    Usa o formato `?dates=AAAAMMDD-BBBBMMDD` suportado pela ESPN (confirmado ao
    vivo com o range 20260628-20260719 que retornou os 32 jogos do mata-mata).

    `deadline` (opcional, em segundos de `time.monotonic()`): se já estourado
    antes da chamada, retorna lista vazia sem fazer I/O.

    Em caso de erro de rede, timeout ou HTTP não-2xx, levanta `EspnClientError`.
    O caller (sync service) captura e trata — nunca propaga até o login.
    """
    if deadline is not None and time.monotonic() >= deadline:
        logger.warning(
            "Deadline já estourado; busca de range %s–%s ignorada.",
            data_inicio,
            data_fim,
        )
        return []

    if timeout_s is None:
        timeout_s = get_settings().espn_timeout_s

    inicio_str = data_inicio.strftime("%Y%m%d")
    fim_str = data_fim.strftime("%Y%m%d")
    url = f"{ESPN_SCOREBOARD_URL}?dates={inicio_str}-{fim_str}"

    client_kwargs: dict = {
        "timeout": httpx.Timeout(timeout_s),
    }
    if _transport is not None:
        client_kwargs["transport"] = _transport

    try:
        with httpx.Client(**client_kwargs) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise EspnClientError(
            f"Timeout ao buscar ESPN para range {inicio_str}-{fim_str}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise EspnClientError(
            f"ESPN retornou HTTP {exc.response.status_code} para range {inicio_str}-{fim_str}"
        ) from exc
    except httpx.RequestError as exc:
        raise EspnClientError(
            f"Erro de rede ao buscar ESPN para range {inicio_str}-{fim_str}"
        ) from exc

    return parse_eventos(payload)


def buscar_scoreboard_com_janela(
    data: date,
    timeout_s: float | None = None,
    deadline: float | None = None,
    _transport: httpx.BaseTransport | None = None,
) -> list[EventoEspn]:
    """Busca D-1, D e D+1 e retorna a união de todos os eventos encontrados.

    Estratégia de robustez contra diferença de fuso horário entre o banco e a ESPN.
    Erros em uma das datas são logados e ignorados (retorna o que conseguiu).

    `deadline` (opcional, em segundos de `time.monotonic()`): orçamento total para
    o conjunto das 3 buscas. Usado no caminho síncrono do dashboard para não travar
    a página se a ESPN estiver lenta. Ao estourar, retorna o que já conseguiu e o
    timeout de cada requisição é reduzido ao tempo restante.
    """
    if timeout_s is None:
        timeout_s = get_settings().espn_timeout_s

    todos: list[EventoEspn] = []
    vistos: set[tuple[str, str]] = set()  # dedup por (abrev_casa, abrev_visitante)

    for delta in (-1, 0, 1):
        timeout_atual = timeout_s
        if deadline is not None:
            restante = deadline - time.monotonic()
            if restante <= 0:
                logger.warning(
                    "Deadline do sync atingido; pulando datas restantes da janela de %s.",
                    data,
                )
                break
            timeout_atual = min(timeout_s, restante)

        d = data + timedelta(days=delta)
        try:
            eventos = buscar_scoreboard(d, timeout_s=timeout_atual, _transport=_transport)
        except EspnClientError as exc:
            logger.warning("ESPN falhou para %s: %s", d, exc)
            continue

        for ev in eventos:
            key = (ev.abrev_casa, ev.abrev_visitante)
            if key not in vistos:
                vistos.add(key)
                todos.append(ev)

    return todos
