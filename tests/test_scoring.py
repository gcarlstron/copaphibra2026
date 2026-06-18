import pytest

from app.services.scoring import calcular_pontos


@pytest.mark.parametrize(
    ("palpite_casa", "palpite_visitante", "oficial_casa", "oficial_visitante", "esperado"),
    [
        (2, 1, 2, 1, 9),
        (2, 0, 2, 1, 6),
        (3, 1, 2, 1, 4),
        (3, 1, 2, 0, 3),
        (1, 0, 0, 2, 0),
    ],
)
def test_calcular_pontos(
    palpite_casa: int,
    palpite_visitante: int,
    oficial_casa: int,
    oficial_visitante: int,
    esperado: int,
) -> None:
    assert calcular_pontos(palpite_casa, palpite_visitante, oficial_casa, oficial_visitante) == esperado


@pytest.mark.parametrize(
    ("palpite_casa", "palpite_visitante", "oficial_casa", "oficial_visitante", "esperado", "descricao"),
    [
        # Borda: empate exato 0x0 palpite 0x0 → 9
        (0, 0, 0, 0, 9, "empate exato 0x0"),
        # Borda: empate com placar errado (palpite 1x1, oficial 2x2) → 6
        (1, 1, 2, 2, 6, "empate placar errado 1x1 vs 2x2"),
    ],
)
def test_calcular_pontos_bordas(
    palpite_casa: int,
    palpite_visitante: int,
    oficial_casa: int,
    oficial_visitante: int,
    esperado: int,
    descricao: str,
) -> None:
    assert calcular_pontos(palpite_casa, palpite_visitante, oficial_casa, oficial_visitante) == esperado, descricao
