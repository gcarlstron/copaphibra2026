"""Tests for ESPN client service (Fase 10c).

Nenhum teste faz chamada de rede real — todos usam fixtures ou MockTransport.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx2 as httpx
import pytest

from app.services.espn import (
    ESPN_STATUS_FULL_TIME,
    EspnClientError,
    EventoEspn,
    buscar_scoreboard,
    buscar_scoreboard_com_janela,
    parse_eventos,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _load_fixture(filename: str) -> dict:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# parse_eventos — parser puro
# ---------------------------------------------------------------------------


class TestParseEventos:
    def test_parses_mex_rsa_full_time(self) -> None:
        """Fixture June 11: MEX 2-0 RSA deve ser parseado corretamente."""
        payload = _load_fixture("espn_20260611.json")
        eventos = parse_eventos(payload)

        mex_rsa = next(
            (e for e in eventos if e.abrev_casa == "MEX" and e.abrev_visitante == "RSA"),
            None,
        )
        assert mex_rsa is not None, "Evento MEX vs RSA não encontrado"
        assert mex_rsa.gols_casa == 2
        assert mex_rsa.gols_visitante == 0
        assert mex_rsa.encerrado is True
        assert mex_rsa.status == ESPN_STATUS_FULL_TIME

    def test_parses_kor_cze_full_time(self) -> None:
        """Fixture June 11: KOR 2-1 CZE deve ser parseado corretamente."""
        payload = _load_fixture("espn_20260611.json")
        eventos = parse_eventos(payload)

        kor_cze = next(
            (e for e in eventos if e.abrev_casa == "KOR" and e.abrev_visitante == "CZE"),
            None,
        )
        assert kor_cze is not None, "Evento KOR vs CZE não encontrado"
        assert kor_cze.gols_casa == 2
        assert kor_cze.gols_visitante == 1
        assert kor_cze.encerrado is True

    def test_ignores_scheduled_events(self) -> None:
        """Eventos STATUS_SCHEDULED devem ser retornados mas encerrado=False."""
        payload = {
            "events": [
                {
                    "competitions": [
                        {
                            "status": {"type": {"name": "STATUS_SCHEDULED"}},
                            "competitors": [
                                {"homeAway": "home", "team": {"abbreviation": "BRA"}, "score": None},
                                {"homeAway": "away", "team": {"abbreviation": "ARG"}, "score": None},
                            ],
                        }
                    ]
                }
            ]
        }
        eventos = parse_eventos(payload)
        assert len(eventos) == 1
        assert eventos[0].encerrado is False
        assert eventos[0].abrev_casa == "BRA"

    def test_ignores_in_progress_events(self) -> None:
        """Eventos STATUS_IN_PROGRESS devem ter encerrado=False."""
        payload = {
            "events": [
                {
                    "competitions": [
                        {
                            "status": {"type": {"name": "STATUS_IN_PROGRESS"}},
                            "competitors": [
                                {"homeAway": "home", "team": {"abbreviation": "FRA"}, "score": "1"},
                                {"homeAway": "away", "team": {"abbreviation": "GER"}, "score": "0"},
                            ],
                        }
                    ]
                }
            ]
        }
        eventos = parse_eventos(payload)
        assert len(eventos) == 1
        assert eventos[0].encerrado is False

    def test_malformed_payload_does_not_raise(self) -> None:
        """Payload com campos faltando não deve levantar exceção."""
        payloads = [
            {},
            {"events": None},
            {"events": [{}]},
            {"events": [{"competitions": []}]},
            {"events": [{"competitions": [{"status": {}, "competitors": [{"homeAway": "home"}]}]}]},
        ]
        for payload in payloads:
            result = parse_eventos(payload)
            assert isinstance(result, list), f"Falhou para payload: {payload}"

    def test_missing_competitions_skipped(self) -> None:
        payload = {"events": [{"id": "1"}]}
        assert parse_eventos(payload) == []

    def test_event_with_only_one_competitor_skipped(self) -> None:
        payload = {
            "events": [
                {
                    "competitions": [
                        {
                            "status": {"type": {"name": "STATUS_FULL_TIME"}},
                            "competitors": [
                                {"homeAway": "home", "team": {"abbreviation": "ESP"}, "score": "3"},
                            ],
                        }
                    ]
                }
            ]
        }
        assert parse_eventos(payload) == []

    def test_both_events_returned_from_fixture(self) -> None:
        """Fixture deve retornar exatamente 2 eventos."""
        payload = _load_fixture("espn_20260611.json")
        eventos = parse_eventos(payload)
        assert len(eventos) == 2
        assert all(e.encerrado for e in eventos)


# ---------------------------------------------------------------------------
# Estado ao vivo (em andamento / intervalo)
# ---------------------------------------------------------------------------


def _payload_status(name: str, state: str, gols_c: str | None = "1", gols_v: str | None = "0") -> dict:
    tipo: dict = {"name": name}
    if state:
        tipo["state"] = state
    return {
        "events": [
            {
                "competitions": [
                    {
                        "status": {"type": tipo},
                        "competitors": [
                            {"homeAway": "home", "team": {"abbreviation": "USA"}, "score": gols_c},
                            {"homeAway": "away", "team": {"abbreviation": "AUS"}, "score": gols_v},
                        ],
                    }
                ]
            }
        ]
    }


class TestEstadoAoVivo:
    def test_em_andamento(self) -> None:
        ev = parse_eventos(_payload_status("STATUS_FIRST_HALF", "in"))[0]
        assert ev.estado == "in"
        assert ev.encerrado is False
        assert ev.ao_vivo is True
        assert ev.no_intervalo is False
        assert ev.gols_casa == 1 and ev.gols_visitante == 0

    def test_intervalo(self) -> None:
        ev = parse_eventos(_payload_status("STATUS_HALFTIME", "in"))[0]
        assert ev.ao_vivo is True
        assert ev.no_intervalo is True


# ---------------------------------------------------------------------------
# Finais do mata-mata (prorrogação / pênaltis) — `status.type.completed`
# ---------------------------------------------------------------------------


def _payload_final(name: str, completed: bool, gols_c: str = "1", gols_v: str = "1") -> dict:
    """Payload de um jogo de mata-mata finalizado (com `completed` e `shootoutScore`)."""
    return {
        "events": [
            {
                "competitions": [
                    {
                        "status": {"type": {"name": name, "state": "post", "completed": completed}},
                        "competitors": [
                            {"homeAway": "home", "team": {"abbreviation": "GER"}, "score": gols_c, "shootoutScore": 3},
                            {"homeAway": "away", "team": {"abbreviation": "PAR"}, "score": gols_v, "shootoutScore": 4},
                        ],
                    }
                ]
            }
        ]
    }


class TestMataMataFinais:
    def test_final_penaltis_encerrado(self) -> None:
        """Jogo decidido nos pênaltis (STATUS_FINAL_PEN) conta como encerrado."""
        ev = parse_eventos(_payload_final("STATUS_FINAL_PEN", True))[0]
        assert ev.encerrado is True
        assert ev.ao_vivo is False
        # Placar do tempo normal; pênaltis (shootoutScore) ficam fora da pontuação.
        assert ev.gols_casa == 1 and ev.gols_visitante == 1

    def test_final_prorrogacao_encerrado(self) -> None:
        """Jogo decidido na prorrogação (STATUS_FINAL_AET) conta como encerrado."""
        ev = parse_eventos(_payload_final("STATUS_FINAL_AET", True, gols_c="2", gols_v="1"))[0]
        assert ev.encerrado is True
        assert ev.ao_vivo is False
        assert ev.gols_casa == 2 and ev.gols_visitante == 1

    def test_completed_false_nao_encerrado(self) -> None:
        """`completed=False` (ex.: ainda rolando) não é encerrado."""
        ev = parse_eventos(_payload_final("STATUS_FINAL_PEN", False))[0]
        assert ev.encerrado is False

    def test_full_time_sem_campo_completed_ainda_encerrado(self) -> None:
        """Fallback por nome: FULL_TIME sem o campo `completed` segue encerrado."""
        ev = parse_eventos(_payload_status("STATUS_FULL_TIME", "post"))[0]
        assert ev.encerrado is True

    def test_agendado_nao_ao_vivo(self) -> None:
        ev = parse_eventos(_payload_status("STATUS_SCHEDULED", "pre", None, None))[0]
        assert ev.ao_vivo is False
        assert ev.no_intervalo is False

    def test_full_time_nao_ao_vivo(self) -> None:
        ev = parse_eventos(_load_fixture("espn_20260611.json"))[0]
        assert ev.encerrado is True
        assert ev.estado == "post"
        assert ev.ao_vivo is False

    def test_fallback_sem_state_in_progress(self) -> None:
        """Sem `state`, um status que não é agendado/cheio é tratado como ao vivo."""
        ev = parse_eventos(_payload_status("STATUS_IN_PROGRESS", ""))[0]
        assert ev.estado == ""
        assert ev.ao_vivo is True

    def test_fallback_sem_state_scheduled(self) -> None:
        ev = parse_eventos(_payload_status("STATUS_SCHEDULED", "", None, None))[0]
        assert ev.estado == ""
        assert ev.ao_vivo is False


# ---------------------------------------------------------------------------
# buscar_scoreboard — HTTP mockado via MockTransport
# ---------------------------------------------------------------------------


class TestBuscarScoreboard:
    def _fixture_transport(self, date_str: str = "20260611") -> httpx.MockTransport:
        """Retorna um MockTransport que responde com a fixture salva."""
        payload = _load_fixture(f"espn_{date_str}.json")
        raw_bytes = json.dumps(payload).encode()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=raw_bytes)

        return httpx.MockTransport(handler)

    def test_returns_events_from_mock(self) -> None:
        transport = self._fixture_transport()
        eventos = buscar_scoreboard(date(2026, 6, 11), _transport=transport)
        assert len(eventos) == 2

    def test_raises_on_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, content=b"Service Unavailable")

        transport = httpx.MockTransport(handler)
        with pytest.raises(EspnClientError):
            buscar_scoreboard(date(2026, 6, 11), _transport=transport)

    def test_raises_on_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        transport = httpx.MockTransport(handler)
        with pytest.raises(EspnClientError):
            buscar_scoreboard(date(2026, 6, 11), _transport=transport)

    def test_raises_on_network_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host", request=request)

        transport = httpx.MockTransport(handler)
        with pytest.raises(EspnClientError):
            buscar_scoreboard(date(2026, 6, 11), _transport=transport)


# ---------------------------------------------------------------------------
# buscar_scoreboard_com_janela — janela D-1/D/D+1 e deadline (ADR-001 / Fase 16)
# ---------------------------------------------------------------------------


class TestBuscarScoreboardComJanela:
    def test_busca_as_tres_datas_sem_deadline(self) -> None:
        """Sem deadline, consulta D-1, D e D+1 (nessa ordem)."""
        chamadas: list[date] = []

        def fake_buscar(d: date, timeout_s=None, _transport=None) -> list[EventoEspn]:
            chamadas.append(d)
            return []

        with patch("app.services.espn.buscar_scoreboard", side_effect=fake_buscar):
            buscar_scoreboard_com_janela(date(2026, 6, 11))

        assert chamadas == [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]

    def test_para_no_meio_da_janela_quando_deadline_estoura(self) -> None:
        """Deadline estourado na 2ª data → para no meio (só D-1 é consultada)."""
        chamadas: list[date] = []

        def fake_buscar(d: date, timeout_s=None, _transport=None) -> list[EventoEspn]:
            chamadas.append(d)
            return [
                EventoEspn(
                    abrev_casa="MEX",
                    abrev_visitante="RSA",
                    gols_casa=1,
                    gols_visitante=0,
                    status=ESPN_STATUS_FULL_TIME,
                    encerrado=True,
                )
            ]

        # monotonic: 1ª iteração dentro do prazo (0.0 < 10); 2ª já estourada (100 > 10).
        with patch(
            "app.services.espn.buscar_scoreboard", side_effect=fake_buscar
        ), patch("app.services.espn.time.monotonic", side_effect=[0.0, 100.0, 100.0]):
            eventos = buscar_scoreboard_com_janela(date(2026, 6, 11), deadline=10.0)

        assert chamadas == [date(2026, 6, 10)]
        assert len(eventos) == 1
