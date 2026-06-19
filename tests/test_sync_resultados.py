"""Tests for sync_resultados service (Fase 10d).

Todos os testes mocam a ESPN — sem rede real.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Jogo, Palpite, Rodada, Usuario
from app.models.sync_state import SyncState
from app.models.team_alias import TeamAlias
from app.services.auth import hash_senha
from app.services.dashboard import STATUS_AGENDADO, STATUS_ENCERRADO
from app.services.espn import EspnClientError, EventoEspn
from app.services.sync_resultados import (
    CHAVE_SYNC,
    ResumoSync,
    _get_or_create_sync_state,
    disparar_sync_se_necessario,
    sincronizar_resultados,
)

# ---------------------------------------------------------------------------
# Fixtures de banco isolado
# ---------------------------------------------------------------------------

_AGORA = datetime(2026, 6, 11, 20, 0, 0, tzinfo=timezone.utc)
_JOGO_DH = datetime(2026, 6, 11, 16, 0, 0, tzinfo=timezone.utc)  # antes de _AGORA


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'sync_test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_base(db: Session) -> tuple[Rodada, Jogo, Usuario, Palpite]:
    """Cria rodada, jogo MEX vs RSA, um usuário e um palpite."""
    rodada = Rodada(nome="Fase de Grupos", ordem=1, aberta=False)
    db.add(rodada)
    db.flush()

    jogo = Jogo(
        rodada_id=rodada.id,
        data_hora=_JOGO_DH,
        time_casa="México",
        time_visitante="África do Sul",
        status=STATUS_AGENDADO,
    )
    db.add(jogo)
    db.flush()

    usuario = Usuario(
        nome="Jogador",
        username="jogador",
        senha_hash=hash_senha("1234"),
        ativo=True,
    )
    db.add(usuario)
    db.flush()

    palpite = Palpite(
        usuario_id=usuario.id,
        jogo_id=jogo.id,
        gols_casa=1,
        gols_visitante=0,
        pontos=0,
        criado_em=_JOGO_DH,
        atualizado_em=_JOGO_DH,
    )
    db.add(palpite)
    db.commit()

    return rodada, jogo, usuario, palpite


def _seed_alias(db: Session, abrev: str, nome_pt: str, nome_en: str = "Name") -> None:
    db.add(TeamAlias(abreviacao=abrev, nome=nome_pt, nome_en=nome_en))
    db.flush()


def _evento_encerrado(
    abrev_casa: str,
    abrev_vis: str,
    gols_c: int,
    gols_v: int,
) -> EventoEspn:
    return EventoEspn(
        abrev_casa=abrev_casa,
        abrev_visitante=abrev_vis,
        gols_casa=gols_c,
        gols_visitante=gols_v,
        status="STATUS_FULL_TIME",
        encerrado=True,
    )


# ---------------------------------------------------------------------------
# sincronizar_resultados — testes unitários
# ---------------------------------------------------------------------------


class TestSincronizarResultados:
    def test_lanca_resultado_pendente(self, db_session: Session) -> None:
        """Jogo pendente que casa com evento ESPN deve ser encerrado com o resultado."""
        _, jogo, _, palpite = _seed_base(db_session)
        _seed_alias(db_session, "MEX", "México")
        _seed_alias(db_session, "RSA", "África do Sul")
        db_session.commit()

        evento = _evento_encerrado("MEX", "RSA", 2, 0)
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_com_janela",
            return_value=[evento],
        ):
            resumo = sincronizar_resultados(db_session, _AGORA)

        assert resumo.lancados == 1
        db_session.refresh(jogo)
        assert jogo.status == STATUS_ENCERRADO
        assert jogo.gols_casa == 2
        assert jogo.gols_visitante == 0

    def test_pontos_recalculados(self, db_session: Session) -> None:
        """Após lancar_resultado, Palpite.pontos deve ser recalculado."""
        _, jogo, _, palpite = _seed_base(db_session)
        _seed_alias(db_session, "MEX", "México")
        _seed_alias(db_session, "RSA", "África do Sul")
        db_session.commit()

        # Palpite: México 1×0 África do Sul — resultado real: 2×0
        # Vencedor certo + gols do perdedor (0) certos = 4 pts
        evento = _evento_encerrado("MEX", "RSA", 2, 0)
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_com_janela",
            return_value=[evento],
        ):
            sincronizar_resultados(db_session, _AGORA)

        db_session.refresh(palpite)
        assert palpite.pontos == 4

    def test_idempotente_jogo_encerrado(self, db_session: Session) -> None:
        """Jogo já encerrado não deve ser relançado."""
        _, jogo, _, _ = _seed_base(db_session)
        jogo.status = STATUS_ENCERRADO
        jogo.gols_casa = 2
        jogo.gols_visitante = 0
        db_session.commit()

        _seed_alias(db_session, "MEX", "México")
        _seed_alias(db_session, "RSA", "África do Sul")
        db_session.commit()

        evento = _evento_encerrado("MEX", "RSA", 3, 1)  # placar diferente
        mock_lancar = MagicMock()
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_com_janela",
            return_value=[evento],
        ), patch("app.services.sync_resultados.lancar_resultado", mock_lancar):
            resumo = sincronizar_resultados(db_session, _AGORA)

        assert resumo.lancados == 0
        mock_lancar.assert_not_called()
        # Placar não deve ter mudado
        db_session.refresh(jogo)
        assert jogo.gols_casa == 2

    def test_abreviacao_sem_depara_conta_e_loga(self, db_session: Session) -> None:
        """Abreviação não mapeada no de-para deve incrementar ignorados_sem_depara."""
        _, jogo, _, _ = _seed_base(db_session)
        # Não insere alias para MEX/RSA
        db_session.commit()

        evento = _evento_encerrado("MEX", "RSA", 2, 0)
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_com_janela",
            return_value=[evento],
        ):
            resumo = sincronizar_resultados(db_session, _AGORA)

        assert resumo.lancados == 0
        assert resumo.ignorados_sem_depara >= 1

    def test_evento_sem_jogo_correspondente_conta(self, db_session: Session) -> None:
        """Evento ESPN encerrado cujos times não existem no banco conta como ignorados_sem_jogo."""
        # Banco com 1 jogo; evento da ESPN é de outro par de times
        rodada = Rodada(nome="Rodada 1", ordem=1, aberta=False)
        db_session.add(rodada)
        db_session.flush()

        jogo = Jogo(
            rodada_id=rodada.id,
            data_hora=_JOGO_DH,
            time_casa="Brasil",
            time_visitante="Marrocos",
            status=STATUS_AGENDADO,
        )
        db_session.add(jogo)
        _seed_alias(db_session, "BRA", "Brasil")
        _seed_alias(db_session, "MAR", "Marrocos")
        _seed_alias(db_session, "ARG", "Argentina")
        _seed_alias(db_session, "GER", "Alemanha")
        db_session.commit()

        # ESPN retorna ARG vs GER (não existe no banco) como encerrado
        evento = _evento_encerrado("ARG", "GER", 1, 0)
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_com_janela",
            return_value=[evento],
        ):
            resumo = sincronizar_resultados(db_session, _AGORA)

        assert resumo.lancados == 0
        assert resumo.ignorados_sem_jogo >= 1

    def test_espn_erro_nao_propaga(self, db_session: Session) -> None:
        """Erro na ESPN (EspnClientError) não deve levantar exceção."""
        _, jogo, _, _ = _seed_base(db_session)
        _seed_alias(db_session, "MEX", "México")
        _seed_alias(db_session, "RSA", "África do Sul")
        db_session.commit()

        with patch(
            "app.services.sync_resultados.buscar_scoreboard_com_janela",
            side_effect=EspnClientError("timeout"),
        ):
            # Não deve levantar
            resumo = sincronizar_resultados(db_session, _AGORA)

        assert resumo.lancados == 0

    def test_sem_jogos_pendentes_retorna_vazio(self, db_session: Session) -> None:
        """Sem jogos pendentes o resumo deve ter tudo zerado."""
        resumo = sincronizar_resultados(db_session, _AGORA)
        assert resumo.lancados == 0
        assert resumo.ignorados_sem_depara == 0
        assert resumo.ignorados_sem_jogo == 0


# ---------------------------------------------------------------------------
# disparar_sync_se_necessario — throttle e isolamento
# ---------------------------------------------------------------------------


class TestDispararSyncSeNecessario:
    def _make_factory(self, db_session: Session):
        """Retorna uma factory que sempre devolve a mesma sessão."""
        def factory():
            return db_session
        return factory

    def test_executa_quando_sem_execucao_anterior(self, db_session: Session) -> None:
        """Sem execução anterior, o sync deve ser chamado."""
        mock_sync = MagicMock(return_value=ResumoSync())
        factory = self._make_factory(db_session)

        with patch("app.services.sync_resultados.sincronizar_resultados", mock_sync):
            disparar_sync_se_necessario(factory, _AGORA)

        mock_sync.assert_called_once()

    def test_throttle_dentro_da_janela(self, db_session: Session) -> None:
        """Segunda chamada dentro da janela de throttle não deve executar sync."""
        # Grava um sync_state com execução recente
        estado = SyncState(chave=CHAVE_SYNC, ultima_execucao=_AGORA)
        db_session.add(estado)
        db_session.commit()

        mock_sync = MagicMock(return_value=ResumoSync())
        factory = self._make_factory(db_session)

        # Chamada 2 minutos depois (< 15 min padrão)
        agora2 = _AGORA.replace(minute=_AGORA.minute + 2)
        with patch("app.services.sync_resultados.sincronizar_resultados", mock_sync), \
             patch(
                "app.services.sync_resultados.get_settings",
                return_value=MagicMock(espn_sync_intervalo_min=15, espn_timeout_s=5),
             ):
            disparar_sync_se_necessario(factory, agora2)

        mock_sync.assert_not_called()

    def test_throttle_apos_janela_executa(self, db_session: Session) -> None:
        """Chamada após a janela de throttle deve executar o sync."""
        estado = SyncState(chave=CHAVE_SYNC, ultima_execucao=_AGORA)
        db_session.add(estado)
        db_session.commit()

        mock_sync = MagicMock(return_value=ResumoSync())
        factory = self._make_factory(db_session)

        # 20 minutos depois (> 15 min padrão)
        from datetime import timedelta
        agora2 = _AGORA + timedelta(minutes=20)
        with patch("app.services.sync_resultados.sincronizar_resultados", mock_sync), \
             patch(
                "app.services.sync_resultados.get_settings",
                return_value=MagicMock(espn_sync_intervalo_min=15, espn_timeout_s=5),
             ):
            disparar_sync_se_necessario(factory, agora2)

        mock_sync.assert_called_once()

    def test_excecao_no_sync_nao_propaga(self, db_session: Session) -> None:
        """Exceção dentro de sincronizar_resultados não deve propagar."""
        factory = self._make_factory(db_session)

        with patch(
            "app.services.sync_resultados.sincronizar_resultados",
            side_effect=RuntimeError("falha catastrófica"),
        ):
            # Não deve levantar
            disparar_sync_se_necessario(factory, _AGORA)

    def test_grava_ultima_execucao(self, db_session: Session) -> None:
        """Após execução, ultima_execucao deve ser gravada no banco."""
        mock_sync = MagicMock(return_value=ResumoSync())
        factory = self._make_factory(db_session)

        with patch("app.services.sync_resultados.sincronizar_resultados", mock_sync):
            disparar_sync_se_necessario(factory, _AGORA)

        estado = db_session.scalar(select(SyncState).where(SyncState.chave == CHAVE_SYNC))
        assert estado is not None
        assert estado.ultima_execucao is not None

    # -----------------------------------------------------------------------
    # Regressão: throttle com ultima_execucao naive (sem tzinfo)
    # -----------------------------------------------------------------------

    def test_throttle_naive_dentro_janela_nao_executa(self, db_session: Session) -> None:
        """SyncState com ultima_execucao NAIVE dentro da janela: não deve executar.

        SQLite devolve datetimes sem tzinfo (naive). O código normaliza para UTC
        antes de comparar. Este teste garante que não há crash ao comparar
        aware × naive e que o throttle funciona corretamente.
        """
        from datetime import timedelta

        # Persiste um timestamp NAIVE (como o SQLite entrega)
        ultima_naive = datetime(2026, 6, 11, 19, 55, 0)  # sem tzinfo
        estado = SyncState(chave=CHAVE_SYNC, ultima_execucao=ultima_naive)
        db_session.add(estado)
        db_session.commit()

        mock_sync = MagicMock(return_value=ResumoSync())
        factory = self._make_factory(db_session)

        # _AGORA é 20:00 UTC; 5 minutos após a ultima_naive (< 15 min)
        with patch("app.services.sync_resultados.sincronizar_resultados", mock_sync), \
             patch(
                "app.services.sync_resultados.get_settings",
                return_value=MagicMock(espn_sync_intervalo_min=15, espn_timeout_s=5),
             ):
            disparar_sync_se_necessario(factory, _AGORA)

        mock_sync.assert_not_called()

    def test_throttle_naive_fora_da_janela_executa(self, db_session: Session) -> None:
        """SyncState com ultima_execucao NAIVE fora da janela: deve executar.

        Garante que a normalização aware×naive não bloqueia chamadas legítimas.
        """
        from datetime import timedelta

        # ultima_execucao NAIVE há 30 minutos atrás
        ultima_naive = datetime(2026, 6, 11, 19, 30, 0)  # sem tzinfo, 30 min antes
        estado = SyncState(chave=CHAVE_SYNC, ultima_execucao=ultima_naive)
        db_session.add(estado)
        db_session.commit()

        mock_sync = MagicMock(return_value=ResumoSync())
        factory = self._make_factory(db_session)

        with patch("app.services.sync_resultados.sincronizar_resultados", mock_sync), \
             patch(
                "app.services.sync_resultados.get_settings",
                return_value=MagicMock(espn_sync_intervalo_min=15, espn_timeout_s=5),
             ):
            disparar_sync_se_necessario(factory, _AGORA)

        mock_sync.assert_called_once()


# ---------------------------------------------------------------------------
# Regressão: home/away invertido na ESPN
# ---------------------------------------------------------------------------


class TestHomeAwayInvertido:
    """A ESPN pode devolver competitors com visitante ANTES do mandante.

    parse_eventos resolve por homeAway, não por posição. Este teste garante que
    gols_casa/gols_visitante ficam no lado certo mesmo com a ordem invertida.
    """

    def _payload_invertido(
        self,
        abrev_casa: str,
        abrev_vis: str,
        gols_c: int,
        gols_v: int,
        status: str = "STATUS_FULL_TIME",
    ) -> dict:
        """Payload onde away vem ANTES de home na lista competitors."""
        return {
            "events": [
                {
                    "competitions": [
                        {
                            "status": {"type": {"name": status}},
                            "competitors": [
                                # away PRIMEIRO — ordem invertida deliberada
                                {
                                    "homeAway": "away",
                                    "team": {"abbreviation": abrev_vis},
                                    "score": str(gols_v),
                                },
                                {
                                    "homeAway": "home",
                                    "team": {"abbreviation": abrev_casa},
                                    "score": str(gols_c),
                                },
                            ],
                        }
                    ]
                }
            ]
        }

    def test_parse_eventos_home_away_invertido(self) -> None:
        """parse_eventos deve resolver homeAway por campo, não por posição."""
        from app.services.espn import parse_eventos

        payload = self._payload_invertido("MEX", "RSA", 2, 0)
        eventos = parse_eventos(payload)

        assert len(eventos) == 1
        ev = eventos[0]
        assert ev.abrev_casa == "MEX"
        assert ev.abrev_visitante == "RSA"
        assert ev.gols_casa == 2
        assert ev.gols_visitante == 0
        assert ev.encerrado is True

    def test_sync_home_away_invertido_lanca_placar_correto(
        self, db_session: Session
    ) -> None:
        """Sync com competitors invertidos deve lançar gols_casa/gols_visitante certos."""
        from app.services.espn import parse_eventos

        # Seed
        rodada = Rodada(nome="Rodada 1", ordem=1, aberta=False)
        db_session.add(rodada)
        db_session.flush()

        jogo = Jogo(
            rodada_id=rodada.id,
            data_hora=_JOGO_DH,
            time_casa="México",
            time_visitante="África do Sul",
            status=STATUS_AGENDADO,
        )
        db_session.add(jogo)
        db_session.add(TeamAlias(abreviacao="MEX", nome="México", nome_en="Mexico"))
        db_session.add(TeamAlias(abreviacao="RSA", nome="África do Sul", nome_en="South Africa"))
        db_session.commit()

        # Payload com away antes de home
        payload = self._payload_invertido("MEX", "RSA", 2, 0)
        eventos = parse_eventos(payload)  # [EventoEspn(casa=MEX, vis=RSA, 2, 0)]

        with patch(
            "app.services.sync_resultados.buscar_scoreboard_com_janela",
            return_value=eventos,
        ):
            resumo = sincronizar_resultados(db_session, _AGORA)

        assert resumo.lancados == 1
        db_session.refresh(jogo)
        assert jogo.gols_casa == 2, "gols_casa deve ser de MEX (mandante)"
        assert jogo.gols_visitante == 0, "gols_visitante deve ser de RSA (visitante)"


# ---------------------------------------------------------------------------
# Regressão: evento encerrado sem placar
# ---------------------------------------------------------------------------


class TestEventoEncerradoSemPlacar:
    """Evento ESPN com encerrado=True mas gols_* None deve ser ignorado sem crash."""

    def test_evento_encerrado_sem_placar_ignorado(self, db_session: Session) -> None:
        rodada = Rodada(nome="Rodada 1", ordem=1, aberta=False)
        db_session.add(rodada)
        db_session.flush()

        jogo = Jogo(
            rodada_id=rodada.id,
            data_hora=_JOGO_DH,
            time_casa="Brasil",
            time_visitante="Argentina",
            status=STATUS_AGENDADO,
        )
        db_session.add(jogo)
        db_session.add(TeamAlias(abreviacao="BRA", nome="Brasil", nome_en="Brazil"))
        db_session.add(TeamAlias(abreviacao="ARG", nome="Argentina", nome_en="Argentina"))
        db_session.commit()

        # Evento encerrado mas sem placar (gols_* = None)
        evento_sem_placar = EventoEspn(
            abrev_casa="BRA",
            abrev_visitante="ARG",
            gols_casa=None,
            gols_visitante=None,
            status="STATUS_FULL_TIME",
            encerrado=True,
        )

        with patch(
            "app.services.sync_resultados.buscar_scoreboard_com_janela",
            return_value=[evento_sem_placar],
        ):
            resumo = sincronizar_resultados(db_session, _AGORA)

        # Não deve lançar, não deve contar em lancados
        assert resumo.lancados == 0
        db_session.refresh(jogo)
        assert jogo.status == STATUS_AGENDADO
