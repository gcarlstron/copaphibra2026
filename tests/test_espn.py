"""Tests for ESPN client service (Fase 10c).

Nenhum teste faz chamada de rede real — todos usam fixtures ou MockTransport.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx2 as httpx
import pytest

from app.services.espn import (
    ESPN_STATUS_FULL_TIME,
    EspnClientError,
    EventoEspn,
    buscar_scoreboard,
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
