"""Cliente ESPN — busca resultados da fase de grupos do Mundial 2026.

Endpoint público (sem auth):
  https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=AAAAMMDD

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

Tratamento de erro em `buscar_scoreboard`:
    Em caso de erro de rede, timeout ou status HTTP não-2xx, a função levanta
    `EspnClientError`. O service de sync captura essa exceção e incrementa o
    contador de ignorados, sem derrubar o sync nem o login.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta

import httpx2 as httpx

from app.config import get_settings

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


def parse_eventos(payload: dict) -> list[EventoEspn]:
    """Converte o payload bruto da ESPN em lista de EventoEspn.

    Defensivo: campos faltando não levantam exceção — o evento é silenciosamente
    descartado com um log WARNING.
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
            encerrado = status_name == ESPN_STATUS_FULL_TIME

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

            eventos.append(
                EventoEspn(
                    abrev_casa=abrev_casa,
                    abrev_visitante=abrev_visitante,
                    gols_casa=gols_casa,
                    gols_visitante=gols_visitante,
                    status=status_name,
                    encerrado=encerrado,
                    estado=estado,
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
