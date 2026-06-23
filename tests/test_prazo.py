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


def test_rodada_importada_fechada_sem_janela_libera_terceiros() -> None:
    """Rodada importada (aberta=False, sem janela) já libera os palpites de todos."""
    agora = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)

    assert rodada_aberta_para_edicao(False, None, None, agora) is False
    assert palpites_de_terceiros_visiveis(False, None, None, agora) is True


def test_rodada_nunca_aberta_sem_janela_e_tratada_como_revelada() -> None:
    """aberta=False + sem janela → 'revelado' (mesma forma da rodada importada).

    Documenta o caso frágil (QA Fase 16): é seguro porque uma rodada que nunca
    foi aberta não tem palpites — `salvar_palpite` revalida a janela, então não há
    palpite de terceiros para vazar mesmo com a visibilidade ligada.
    """
    agora = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)

    assert palpites_de_terceiros_visiveis(False, None, None, agora) is True


def test_rodada_agendada_abertura_futura_oculta_terceiros() -> None:
    """Pré-abertura (abertura no futuro): não edita ainda e terceiros seguem ocultos."""
    agora = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    abertura = agora + timedelta(hours=2)
    fechamento = agora + timedelta(hours=4)

    assert rodada_aberta_para_edicao(True, abertura, fechamento, agora) is False
    assert palpites_de_terceiros_visiveis(True, abertura, fechamento, agora) is False


def test_rodada_aberta_fechamento_futuro_oculta_terceiros() -> None:
    """Janela ainda aberta (fechamento no futuro): terceiros ocultos."""
    agora = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    abertura = agora - timedelta(hours=1)
    fechamento = agora + timedelta(hours=2)

    assert rodada_aberta_para_edicao(True, abertura, fechamento, agora) is True
    assert palpites_de_terceiros_visiveis(True, abertura, fechamento, agora) is False
