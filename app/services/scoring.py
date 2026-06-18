from __future__ import annotations


def _resultado(casa: int, visitante: int) -> int:
    if casa > visitante:
        return 1
    if casa < visitante:
        return -1
    return 0


def calcular_pontos(
    palpite_casa: int,
    palpite_visitante: int,
    oficial_casa: int,
    oficial_visitante: int,
) -> int:
    resultado_palpite = _resultado(palpite_casa, palpite_visitante)
    resultado_oficial = _resultado(oficial_casa, oficial_visitante)

    if resultado_palpite != resultado_oficial:
        return 0

    if palpite_casa == oficial_casa and palpite_visitante == oficial_visitante:
        return 9

    if resultado_oficial == 0:
        return 6

    if resultado_oficial == 1:
        gols_vencedor_palpite = palpite_casa
        gols_vencedor_oficial = oficial_casa
        gols_perdedor_palpite = palpite_visitante
        gols_perdedor_oficial = oficial_visitante
    else:
        gols_vencedor_palpite = palpite_visitante
        gols_vencedor_oficial = oficial_visitante
        gols_perdedor_palpite = palpite_casa
        gols_perdedor_oficial = oficial_casa

    if gols_vencedor_palpite == gols_vencedor_oficial:
        return 6

    if gols_perdedor_palpite == gols_perdedor_oficial:
        return 4

    return 3
