from app.services.ranking import chave_de_ranking, contar_buckets_de_pontos


def test_contar_buckets_de_pontos() -> None:
    assert contar_buckets_de_pontos([9, 6, 6, 4, 3, 0, 9]) == {9: 2, 6: 2, 4: 1, 3: 1}


def test_chave_de_ranking_ordena_por_total_e_desempate() -> None:
    assert chave_de_ranking(120, 4, 3, 2, 1) > chave_de_ranking(120, 3, 4, 2, 1)
