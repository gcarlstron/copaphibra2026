"""Tests for ESPN service — Fase 17 (mata-mata).

Cobre:
  - parse_eventos: event_id, season_slug, data_hora (UTC→fuso-dos-dados), nomes ESPN.
  - fase_do_slug: todos os slugs válidos e um inválido.
  - buscar_scoreboard_range: monta URL com range; MockTransport; erros.
  - Compatibilidade: testes que instanciam EventoEspn sem os novos campos continuam ok.

Sem rede — todos os testes usam fixtures ou MockTransport.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx2 as httpx
import pytest

from app.services.espn import (
    EspnClientError,
    EventoEspn,
    FASES_MATA_MATA,
    buscar_scoreboard_range,
    fase_do_slug,
    parse_eventos,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(filename: str) -> dict:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# fase_do_slug
# ---------------------------------------------------------------------------


class TestFaseDoSlug:
    def test_todos_os_slugs_validos(self) -> None:
        slugs_esperados = [
            ("round-of-32", 4, "16-avos de final"),
            ("round-of-16", 5, "Oitavas de final"),
            ("quarterfinals", 6, "Quartas de final"),
            ("semifinals", 7, "Semifinais"),
            ("3rd-place-match", 8, "Disputa de 3º lugar"),
            ("final", 9, "Final"),
        ]
        for slug, ordem_esp, nome_esp in slugs_esperados:
            resultado = fase_do_slug(slug)
            assert resultado is not None, f"fase_do_slug({slug!r}) retornou None"
            ordem, nome = resultado
            assert ordem == ordem_esp, f"{slug}: ordem={ordem}, esperado={ordem_esp}"
            assert nome == nome_esp, f"{slug}: nome={nome!r}, esperado={nome_esp!r}"

    def test_slug_fase_de_grupos_retorna_none(self) -> None:
        assert fase_do_slug("group-stage") is None

    def test_slug_vazio_retorna_none(self) -> None:
        assert fase_do_slug("") is None

    def test_slug_inexistente_retorna_none(self) -> None:
        assert fase_do_slug("xyz-unknown") is None

    def test_3rd_place_typo_retorna_none(self) -> None:
        """Garante que '3rd-place' (sem '-match') não é aceito — slug real é '3rd-place-match'."""
        assert fase_do_slug("3rd-place") is None

    def test_fases_mata_mata_tem_seis_entradas(self) -> None:
        assert len(FASES_MATA_MATA) == 6

    def test_ordens_sao_unicas(self) -> None:
        ordens = [v[0] for v in FASES_MATA_MATA.values()]
        assert len(ordens) == len(set(ordens))


# ---------------------------------------------------------------------------
# parse_eventos — novos campos (event_id, season_slug, data_hora, nomes ESPN)
# ---------------------------------------------------------------------------


class TestParseEventosMataMata:
    """Testa os campos adicionados na Fase 17 sem quebrar os testes antigos."""

    def _payload_ko(
        self,
        event_id: str = "760486",
        slug: str = "round-of-32",
        date_str: str = "2026-06-28T19:00Z",
        abrev_casa: str = "RSA",
        abrev_vis: str = "CAN",
        display_casa: str = "South Africa",
        display_vis: str = "Canada",
        status: str = "STATUS_SCHEDULED",
        state: str = "pre",
    ) -> dict:
        return {
            "events": [
                {
                    "id": event_id,
                    "date": date_str,
                    "season": {"slug": slug},
                    "competitions": [
                        {
                            "status": {"type": {"name": status, "state": state}},
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "score": None,
                                    "team": {
                                        "abbreviation": abrev_casa,
                                        "displayName": display_casa,
                                        "name": display_casa,
                                    },
                                },
                                {
                                    "homeAway": "away",
                                    "score": None,
                                    "team": {
                                        "abbreviation": abrev_vis,
                                        "displayName": display_vis,
                                        "name": display_vis,
                                    },
                                },
                            ],
                        }
                    ],
                }
            ]
        }

    def test_event_id_preenchido(self) -> None:
        eventos = parse_eventos(self._payload_ko(event_id="760486"))
        assert len(eventos) == 1
        assert eventos[0].event_id == "760486"

    def test_season_slug_preenchido(self) -> None:
        eventos = parse_eventos(self._payload_ko(slug="round-of-32"))
        assert eventos[0].season_slug == "round-of-32"

    def test_data_hora_convertida_para_fuso_dos_dados(self) -> None:
        """ESPN retorna 2026-06-28T19:00Z (UTC). Deve virar 2026-06-28T16:00 "UTC" (BRT)."""
        eventos = parse_eventos(self._payload_ko(date_str="2026-06-28T19:00Z"))
        dh = eventos[0].data_hora
        assert dh is not None
        # BRT = UTC-3 → 19:00 UTC = 16:00 BRT, gravado com label UTC
        assert dh.hour == 16
        assert dh.minute == 0
        assert dh.day == 28
        assert dh.month == 6
        # tzinfo deve ser UTC (convenção BRT-rotulado-UTC)
        assert dh.tzinfo == timezone.utc

    def test_data_hora_formato_alternativo(self) -> None:
        """Aceita ISO 8601 com offset explícito, não só 'Z'."""
        eventos = parse_eventos(self._payload_ko(date_str="2026-07-04T19:00:00+00:00"))
        dh = eventos[0].data_hora
        assert dh is not None
        assert dh.hour == 16  # 19:00 UTC → 16:00 BRT

    def test_data_hora_invalida_retorna_none(self) -> None:
        payload = self._payload_ko()
        payload["events"][0]["date"] = "nao-e-data"
        eventos = parse_eventos(payload)
        assert eventos[0].data_hora is None

    def test_data_hora_ausente_retorna_none(self) -> None:
        payload = self._payload_ko()
        del payload["events"][0]["date"]
        eventos = parse_eventos(payload)
        assert eventos[0].data_hora is None

    def test_nomes_espn_times_reais(self) -> None:
        """Times reais: displayName preenchido corretamente."""
        eventos = parse_eventos(
            self._payload_ko(display_casa="South Africa", display_vis="Canada")
        )
        assert eventos[0].nome_casa_espn == "South Africa"
        assert eventos[0].nome_visitante_espn == "Canada"

    def test_nomes_espn_placeholders(self) -> None:
        """Placeholders: displayName é o texto descritivo ('Round of 32 1 Winner')."""
        eventos = parse_eventos(
            self._payload_ko(
                abrev_casa="RD32",
                abrev_vis="RD32",
                display_casa="Round of 32 1 Winner",
                display_vis="Round of 32 2 Winner",
            )
        )
        assert eventos[0].nome_casa_espn == "Round of 32 1 Winner"
        assert eventos[0].nome_visitante_espn == "Round of 32 2 Winner"

    def test_fixture_ko_range_tem_todos_os_slugs(self) -> None:
        """A fixture ko_range deve conter um evento para cada slug do mata-mata."""
        payload = _load_fixture("espn_ko_range.json")
        eventos = parse_eventos(payload)
        slugs = {ev.season_slug for ev in eventos}
        for slug in FASES_MATA_MATA:
            assert slug in slugs, f"Slug {slug!r} não encontrado na fixture"

    def test_fixture_ko_range_r32_tem_times_reais(self) -> None:
        """Evento do R32 na fixture tem abreviações reais (RSA/CAN), não placeholders."""
        payload = _load_fixture("espn_ko_range.json")
        eventos = parse_eventos(payload)
        r32 = next((ev for ev in eventos if ev.season_slug == "round-of-32"), None)
        assert r32 is not None
        assert r32.abrev_casa == "RSA"
        assert r32.abrev_visitante == "CAN"
        assert r32.event_id == "760486"

    def test_fixture_ko_range_r16_tem_placeholder(self) -> None:
        """Evento do R16 na fixture usa 'RD32' como abreviação (placeholder)."""
        payload = _load_fixture("espn_ko_range.json")
        eventos = parse_eventos(payload)
        r16 = next((ev for ev in eventos if ev.season_slug == "round-of-16"), None)
        assert r16 is not None
        assert r16.abrev_casa == "RD32"
        assert r16.nome_casa_espn == "Round of 32 1 Winner"

    def test_compatibilidade_instancia_sem_novos_campos(self) -> None:
        """EventoEspn instanciado sem os campos da Fase 17 usa defaults seguros."""
        ev = EventoEspn(
            abrev_casa="BRA",
            abrev_visitante="ARG",
            gols_casa=1,
            gols_visitante=0,
            status="STATUS_FULL_TIME",
            encerrado=True,
        )
        assert ev.event_id == ""
        assert ev.season_slug == ""
        assert ev.data_hora is None
        assert ev.nome_casa_espn == ""
        assert ev.nome_visitante_espn == ""
        # Propriedades existentes não quebraram
        assert ev.encerrado is True
        assert ev.ao_vivo is False

    def test_grupo_stage_preserva_dados_existentes(self) -> None:
        """Fixture de grupo-stage continua funcionando (season_slug='group-stage')."""
        payload = _load_fixture("espn_ko_range.json")
        eventos = parse_eventos(payload)
        grupo = next((ev for ev in eventos if ev.season_slug == "group-stage"), None)
        assert grupo is not None
        assert grupo.abrev_casa == "MEX"
        assert grupo.gols_casa == 2
        assert grupo.encerrado is True


# ---------------------------------------------------------------------------
# buscar_scoreboard_range — HTTP mockado via MockTransport
# ---------------------------------------------------------------------------


class TestBuscarScoreboardRange:
    def _fixture_transport(self, fixture: str = "espn_ko_range.json") -> httpx.MockTransport:
        payload = _load_fixture(fixture)
        raw_bytes = json.dumps(payload).encode()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=raw_bytes)

        return httpx.MockTransport(handler)

    def test_retorna_eventos_do_mock(self) -> None:
        transport = self._fixture_transport()
        eventos = buscar_scoreboard_range(
            date(2026, 6, 28), date(2026, 7, 19), _transport=transport
        )
        assert len(eventos) > 0

    def test_url_tem_formato_range(self) -> None:
        """A URL montada deve conter o formato dates=AAAAMMDD-BBBBMMDD."""
        urls_capturadas: list[str] = []

        payload = _load_fixture("espn_ko_range.json")
        raw_bytes = json.dumps(payload).encode()

        def handler(request: httpx.Request) -> httpx.Response:
            urls_capturadas.append(str(request.url))
            return httpx.Response(200, content=raw_bytes)

        transport = httpx.MockTransport(handler)
        buscar_scoreboard_range(
            date(2026, 6, 28), date(2026, 7, 19), _transport=transport
        )

        assert len(urls_capturadas) == 1, "Deve fazer exatamente 1 chamada HTTP"
        assert "dates=20260628-20260719" in urls_capturadas[0]

    def test_levanta_espn_client_error_em_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, content=b"Service Unavailable")

        transport = httpx.MockTransport(handler)
        with pytest.raises(EspnClientError):
            buscar_scoreboard_range(
                date(2026, 6, 28), date(2026, 7, 19), _transport=transport
            )

    def test_levanta_espn_client_error_em_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        transport = httpx.MockTransport(handler)
        with pytest.raises(EspnClientError):
            buscar_scoreboard_range(
                date(2026, 6, 28), date(2026, 7, 19), _transport=transport
            )

    def test_levanta_espn_client_error_em_erro_de_rede(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host", request=request)

        transport = httpx.MockTransport(handler)
        with pytest.raises(EspnClientError):
            buscar_scoreboard_range(
                date(2026, 6, 28), date(2026, 7, 19), _transport=transport
            )

    def test_deadline_ja_estourado_retorna_lista_vazia(self) -> None:
        """Se o deadline já passou antes da chamada, retorna [] sem fazer I/O."""
        urls_capturadas: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            urls_capturadas.append(str(request.url))
            return httpx.Response(200, content=b'{"events":[]}')

        transport = httpx.MockTransport(handler)

        with patch("app.services.espn.time.monotonic", return_value=1000.0):
            eventos = buscar_scoreboard_range(
                date(2026, 6, 28), date(2026, 7, 19), deadline=10.0, _transport=transport
            )

        assert eventos == []
        assert urls_capturadas == [], "Não deve ter feito nenhuma chamada HTTP"

    def test_uma_unica_chamada_http(self) -> None:
        """Ao contrário de buscar_scoreboard_com_janela (3 datas), esta faz 1 chamada."""
        contagem: list[int] = [0]

        payload = _load_fixture("espn_ko_range.json")
        raw_bytes = json.dumps(payload).encode()

        def handler(request: httpx.Request) -> httpx.Response:
            contagem[0] += 1
            return httpx.Response(200, content=raw_bytes)

        transport = httpx.MockTransport(handler)
        buscar_scoreboard_range(
            date(2026, 6, 28), date(2026, 7, 19), _transport=transport
        )
        assert contagem[0] == 1
