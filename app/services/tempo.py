"""Fuso dos dados e "agora" consistente (ADR-002).

Os horários de jogos e rodadas foram importados da planilha como **hora local
(BRT, UTC-3)** mas gravados no banco com **label UTC** (ver
`scripts/importar_planilha.py` e o `_parse_data_hora` do admin, que fazem
`datetime(..., tzinfo=timezone.utc)` sobre o relógio de parede local).

Para que comparações de prazo e detecção de "ao vivo/iminente" batam com esses
dados, o "agora" precisa estar na **mesma convenção**: o relógio de parede atual
em BRT, rotulado como UTC. Comparar os dados (BRT-rotulado-UTC) contra
`datetime.now(timezone.utc)` (UTC real) gera um deslocamento de ~3h — inofensivo
na fase de grupos por coincidência das janelas, mas com risco no mata-mata.

Decisão (ADR-002): alinhar o "agora" ao fuso dos dados (esta abordagem), em vez
de reescrever os dados para UTC real — o que quebraria o casamento de datas com
a ESPN, que agrupa por `date(Jogo.data_hora)` no calendário BRT.

O Brasil não observa horário de verão desde 2019, então BRT é um offset fixo de
UTC-3 — usamos `timezone(timedelta(hours=-3))` e evitamos a dependência de uma
base de fusos (tzdata), que não existe por padrão no Windows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Fuso dos dados: BRT fixo em UTC-3 (sem horário de verão desde 2019).
FUSO_DADOS = timezone(timedelta(hours=-3))


def em_fuso_dos_dados(instante: datetime) -> datetime:
    """Converte um instante para o relógio de parede BRT, rotulado como UTC.

    Aceita datetimes aware ou naive (naive é tratado como UTC). O retorno tem os
    campos do relógio BRT mas `tzinfo=UTC`, casando com a convenção do banco.
    """
    aware = instante if instante.tzinfo is not None else instante.replace(tzinfo=timezone.utc)
    return aware.astimezone(FUSO_DADOS).replace(tzinfo=timezone.utc)


def agora() -> datetime:
    """Instante atual no fuso dos dados (BRT), rotulado como UTC."""
    return em_fuso_dos_dados(datetime.now(timezone.utc))
