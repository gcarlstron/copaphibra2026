from __future__ import annotations

from datetime import datetime
from datetime import timezone


def _normalizar_datetime(valor: datetime | None) -> datetime | None:
    if valor is None:
        return None
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor


def rodada_aberta_para_edicao(
    aberta: bool,
    abertura: datetime | None,
    fechamento: datetime | None,
    agora: datetime,
) -> bool:
    abertura_normalizada = _normalizar_datetime(abertura)
    fechamento_normalizado = _normalizar_datetime(fechamento)
    agora_normalizado = _normalizar_datetime(agora)

    assert agora_normalizado is not None

    if not aberta:
        return False

    if abertura_normalizada is not None and agora_normalizado < abertura_normalizada:
        return False

    if fechamento_normalizado is not None and agora_normalizado > fechamento_normalizado:
        return False

    return True


def palpites_de_terceiros_visiveis(
    aberta: bool,
    abertura: datetime | None,
    fechamento: datetime | None,
    agora: datetime,
) -> bool:
    abertura_normalizada = _normalizar_datetime(abertura)
    fechamento_normalizado = _normalizar_datetime(fechamento)
    agora_normalizado = _normalizar_datetime(agora)

    assert agora_normalizado is not None

    if rodada_aberta_para_edicao(aberta, abertura, fechamento, agora):
        return False

    if fechamento_normalizado is None:
        return not aberta

    return agora_normalizado > fechamento_normalizado
