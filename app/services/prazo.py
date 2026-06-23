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
    """Os palpites de TODOS ficam visíveis só depois que a rodada fecha (Regra #4).

    - Rodada aberta para edição agora → False (sigilo durante a janela).
    - Com `fechamento` definido → True só quando `agora` passou do fechamento.
    - Sem `fechamento` (janela aberta) → revela quando `aberta=False`.

    O caso `aberta=False, fechamento=None → True` é **intencional**: cobre as
    rodadas importadas/encerradas (a carga inicial grava `aberta=False` sem
    janela) e precisa liberar os palpites de todos. Uma rodada NOVA, criada pelo
    admin e ainda não aberta, também cai aqui — mas é **seguro**: `salvar_palpite`
    revalida `rodada_aberta_para_edicao`, então uma rodada que nunca foi aberta
    não tem palpite de ninguém para vazar (não há o que revelar). Operacional: ao
    montar uma rodada nova, abra-a antes de divulgar o link do detalhe do jogo.
    """
    abertura_normalizada = _normalizar_datetime(abertura)
    fechamento_normalizado = _normalizar_datetime(fechamento)
    agora_normalizado = _normalizar_datetime(agora)

    assert agora_normalizado is not None

    if rodada_aberta_para_edicao(aberta, abertura, fechamento, agora):
        return False

    if fechamento_normalizado is None:
        return not aberta

    return agora_normalizado > fechamento_normalizado
