from datetime import datetime, timedelta, timezone

from app.services.prazo import palpites_de_terceiros_visiveis, rodada_aberta_para_edicao


def test_rodada_aberta_sem_janela() -> None:
    agora = datetime.now(timezone.utc)

    assert rodada_aberta_para_edicao(True, None, None, agora) is True


def test_rodada_fechada_por_data() -> None:
    agora = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    abertura = agora - timedelta(hours=2)
    fechamento = agora - timedelta(minutes=1)

    assert rodada_aberta_para_edicao(True, abertura, fechamento, agora) is False


def test_palpites_terceiros_so_apos_fechamento() -> None:
    agora = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    abertura = agora - timedelta(hours=2)
    fechamento = agora - timedelta(minutes=1)

    assert palpites_de_terceiros_visiveis(True, abertura, fechamento, agora) is True
