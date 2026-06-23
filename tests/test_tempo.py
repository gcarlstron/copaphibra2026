"""Testes do fuso dos dados (ADR-002).

Garante que o "agora" usado nas comparações fica no relógio de parede BRT
(rotulado UTC), alinhado com os horários gravados pelo importador/admin —
e que isso corrige o deslocamento de ~3h que apareceria no mata-mata.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.prazo import rodada_aberta_para_edicao
from app.services.tempo import FUSO_DADOS, agora, em_fuso_dos_dados


def test_fuso_dados_e_utc_menos_3() -> None:
    assert FUSO_DADOS.utcoffset(None) == timedelta(hours=-3)


def test_em_fuso_dos_dados_relabela_relogio_brt_como_utc() -> None:
    # 21:30 UTC reais → 18:30 BRT → rotulado como 18:30 UTC.
    instante = datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)
    resultado = em_fuso_dos_dados(instante)
    assert resultado == datetime(2026, 7, 5, 18, 30, tzinfo=timezone.utc)
    assert resultado.tzinfo == timezone.utc


def test_agora_esta_3h_atras_do_utc_real() -> None:
    """`agora()` é o relógio BRT rotulado UTC → ~3h "atrás" do UTC real."""
    utc_real = datetime.now(timezone.utc)
    delta = utc_real - agora()
    assert timedelta(hours=2, minutes=59) <= delta <= timedelta(hours=3, minutes=1)


def test_mata_mata_prazo_respeita_fuso_brt() -> None:
    """Cenário mata-mata: rodada fecha às 20:00 BRT (gravado como 20:00 UTC-label).

    Momento real: 21:30 UTC = 18:30 BRT → ainda faltam 1h30 para o fechamento,
    logo a rodada deve estar ABERTA. Com o "agora" no fuso dos dados isso é
    correto; comparar com o UTC real (bug antigo) a daria como FECHADA.
    """
    fechamento = datetime(2026, 7, 5, 20, 0, tzinfo=timezone.utc)  # 20:00 BRT-rotulado-UTC
    instante_real = datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)

    agora_dados = em_fuso_dos_dados(instante_real)
    assert rodada_aberta_para_edicao(True, None, fechamento, agora_dados) is True

    # Sanidade: o bug antigo (comparar com o UTC real) fecharia a rodada cedo demais.
    assert rodada_aberta_para_edicao(True, None, fechamento, instante_real) is False
