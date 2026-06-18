from __future__ import annotations

from collections.abc import Iterable


def contar_buckets_de_pontos(pontos: Iterable[int]) -> dict[int, int]:
    contagem = {9: 0, 6: 0, 4: 0, 3: 0}
    for ponto in pontos:
        if ponto in contagem:
            contagem[ponto] += 1
    return contagem


def chave_de_ranking(total: int, qtd_9: int, qtd_6: int, qtd_4: int, qtd_3: int) -> tuple[int, int, int, int, int]:
    return (total, qtd_9, qtd_6, qtd_4, qtd_3)
