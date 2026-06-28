"""Tests for ingestão do mata-mata via ESPN (Fase 17).

Cobre:
  - Criação de rodadas e jogos agendados (R32 com times reais, R16 com placeholders).
  - Resolução in-place: placeholder criado → depois update com time real, palpite preservado.
  - Idempotência: 2ª execução não duplica nem reabre rodada.
  - Não sobrescreve jogo ENCERRADO.
  - deadline estourado → pula a busca.
  - Range sem eventos KO → no-op na fase de grupos.
  - Contadores do ResumoSync corretos.

Sem rede real — todos os testes usam patch/MockTransport.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Jogo, Palpite, Rodada, Usuario
from app.models.team_alias import TeamAlias
from app.services.auth import hash_senha
from app.services.dashboard import STATUS_AGENDADO, STATUS_ENCERRADO
from app.services.espn import EventoEspn, EspnClientError
from app.services.sync_resultados import ingerir_jogos_mata_mata, sincronizar_resultados

# "Agora" usado nos testes: 28/06 às 12:00 UTC (antes dos jogos do R32)
_AGORA = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)

# data_hora de um jogo R32 real: 28/06/2026 às 19:00 UTC = 16:00 BRT
_DH_R32 = datetime(2026, 6, 28, 16, 0, 0, tzinfo=timezone.utc)  # BRT-rotulado-UTC


# ---------------------------------------------------------------------------
# Fixtures de banco isolado
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ko_test.db'}",
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


def _seed_alias(db: Session, abrev: str, nome_pt: str) -> None:
    db.add(TeamAlias(abreviacao=abrev, nome=nome_pt, nome_en=nome_pt))
    db.flush()


def _evento_ko_real(
    event_id: str = "760486",
    slug: str = "round-of-32",
    data_hora: datetime | None = None,
    abrev_casa: str = "RSA",
    abrev_vis: str = "CAN",
    nome_casa: str = "South Africa",
    nome_vis: str = "Canada",
    encerrado: bool = False,
    gols_c: int | None = None,
    gols_v: int | None = None,
) -> EventoEspn:
    if data_hora is None:
        data_hora = _DH_R32
    return EventoEspn(
        abrev_casa=abrev_casa,
        abrev_visitante=abrev_vis,
        gols_casa=gols_c,
        gols_visitante=gols_v,
        status="STATUS_FULL_TIME" if encerrado else "STATUS_SCHEDULED",
        encerrado=encerrado,
        estado="post" if encerrado else "pre",
        event_id=event_id,
        season_slug=slug,
        data_hora=data_hora,
        nome_casa_espn=nome_casa,
        nome_visitante_espn=nome_vis,
    )


def _evento_ko_placeholder(
    event_id: str = "760490",
    slug: str = "round-of-16",
    data_hora: datetime | None = None,
    nome_casa: str = "Round of 32 1 Winner",
    nome_vis: str = "Round of 32 2 Winner",
) -> EventoEspn:
    if data_hora is None:
        data_hora = datetime(2026, 7, 4, 16, 0, 0, tzinfo=timezone.utc)
    return EventoEspn(
        abrev_casa="RD32",
        abrev_visitante="RD32",
        gols_casa=None,
        gols_visitante=None,
        status="STATUS_SCHEDULED",
        encerrado=False,
        estado="pre",
        event_id=event_id,
        season_slug=slug,
        data_hora=data_hora,
        nome_casa_espn=nome_casa,
        nome_visitante_espn=nome_vis,
    )


# ---------------------------------------------------------------------------
# ingerir_jogos_mata_mata — testes unitários
# ---------------------------------------------------------------------------


class TestIngerirJogosMataMata:
    def test_cria_rodada_e_jogo_r32(self, db_session: Session) -> None:
        """R32 com times reais: rodada e jogo criados com dados corretos."""
        _seed_alias(db_session, "RSA", "África do Sul")
        _seed_alias(db_session, "CAN", "Canadá")
        db_session.commit()

        evento = _evento_ko_real()
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=[evento],
        ):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert resumo.rodadas_criadas == 1
        assert resumo.jogos_criados == 1
        assert resumo.jogos_atualizados_ko == 0

        rodada = db_session.scalar(select(Rodada).where(Rodada.ordem == 4))
        assert rodada is not None
        assert rodada.nome == "16-avos de final"
        assert rodada.aberta is False  # admin abre manualmente

        jogo = db_session.scalar(select(Jogo).where(Jogo.espn_event_id == "760486"))
        assert jogo is not None
        assert jogo.time_casa == "África do Sul"  # de-para PT
        assert jogo.time_visitante == "Canadá"
        assert jogo.status == STATUS_AGENDADO
        # SQLite devolve datetimes naive — compara a parte temporal sem tzinfo
        dh = jogo.data_hora
        dh_naive = dh.replace(tzinfo=None) if dh.tzinfo else dh
        assert dh_naive == _DH_R32.replace(tzinfo=None)

    def test_cria_jogo_placeholder_com_nome_espn(self, db_session: Session) -> None:
        """Placeholder (R16 sem times): usa displayName da ESPN como nome."""
        db_session.commit()

        evento = _evento_ko_placeholder()
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=[evento],
        ):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert resumo.jogos_criados == 1

        jogo = db_session.scalar(select(Jogo).where(Jogo.espn_event_id == "760490"))
        assert jogo is not None
        assert jogo.time_casa == "Round of 32 1 Winner"
        assert jogo.time_visitante == "Round of 32 2 Winner"

    def test_resolucao_inplace_preserva_palpite(self, db_session: Session) -> None:
        """Placeholder criado → 2ª execução com times reais atualiza nomes, palpite intacto."""
        db_session.commit()

        # 1ª execução: cria jogo com placeholder
        placeholder = _evento_ko_placeholder(event_id="760490", slug="round-of-16")
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=[placeholder],
        ):
            ingerir_jogos_mata_mata(db_session, _AGORA)

        jogo = db_session.scalar(select(Jogo).where(Jogo.espn_event_id == "760490"))
        assert jogo is not None
        jogo_id_original = jogo.id

        # Cria um palpite no jogo placeholder
        usuario = Usuario(
            nome="Teste",
            username="teste",
            senha_hash=hash_senha("1234"),
            ativo=True,
        )
        db_session.add(usuario)
        db_session.flush()

        palpite = Palpite(
            usuario_id=usuario.id,
            jogo_id=jogo.id,
            gols_casa=2,
            gols_visitante=1,
            pontos=0,
            criado_em=_AGORA,
            atualizado_em=_AGORA,
        )
        db_session.add(palpite)
        db_session.commit()

        # 2ª execução: agora o R32 foi disputado, R16 tem times reais
        _seed_alias(db_session, "BRA", "Brasil")
        _seed_alias(db_session, "ARG", "Argentina")
        db_session.commit()

        evento_real = EventoEspn(
            abrev_casa="BRA",
            abrev_visitante="ARG",
            gols_casa=None,
            gols_visitante=None,
            status="STATUS_SCHEDULED",
            encerrado=False,
            estado="pre",
            event_id="760490",
            season_slug="round-of-16",
            data_hora=datetime(2026, 7, 4, 16, 0, 0, tzinfo=timezone.utc),
            nome_casa_espn="Brazil",
            nome_visitante_espn="Argentina",
        )
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=[evento_real],
        ):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert resumo.jogos_criados == 0
        assert resumo.jogos_atualizados_ko == 1

        # MESMO jogo_id — não foi recriado
        db_session.refresh(jogo)
        assert jogo.id == jogo_id_original
        assert jogo.time_casa == "Brasil"  # de-para PT vence sobre displayName ESPN
        assert jogo.time_visitante == "Argentina"

        # Palpite sobreviveu com o mesmo jogo_id
        db_session.refresh(palpite)
        assert palpite.jogo_id == jogo_id_original
        assert palpite.gols_casa == 2
        assert palpite.gols_visitante == 1

    def test_idempotente_segunda_execucao_nao_duplica(self, db_session: Session) -> None:
        """Rodar duas vezes não duplica rodadas nem jogos."""
        db_session.commit()

        evento = _evento_ko_real()
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=[evento],
        ):
            r1 = ingerir_jogos_mata_mata(db_session, _AGORA)
            # Expira a sessão para a 2ª execução reler do banco (no SQLite o
            # data_hora volta naive — expõe comparação naive×aware espúria).
            db_session.expire_all()
            r2 = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert r1.rodadas_criadas == 1
        assert r1.jogos_criados == 1
        assert r2.rodadas_criadas == 0
        assert r2.jogos_criados == 0
        assert r2.jogos_atualizados_ko == 0  # idempotente real: sem update espúrio

        # Só deve existir 1 rodada e 1 jogo
        rodadas = db_session.scalars(select(Rodada).where(Rodada.ordem == 4)).all()
        assert len(rodadas) == 1
        jogos = db_session.scalars(
            select(Jogo).where(Jogo.espn_event_id == "760486")
        ).all()
        assert len(jogos) == 1

    def test_nao_reabre_rodada_existente(self, db_session: Session) -> None:
        """Se a rodada já existe (aberta=True), não muda o campo aberta."""
        # Cria rodada já aberta (admin abriu manualmente)
        rodada = Rodada(nome="16-avos de final", ordem=4, aberta=True)
        db_session.add(rodada)
        db_session.commit()

        evento = _evento_ko_real()
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=[evento],
        ):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert resumo.rodadas_criadas == 0  # não criou (já existia)

        db_session.refresh(rodada)
        assert rodada.aberta is True  # não fechou a rodada que estava aberta

    def test_nao_sobrescreve_jogo_encerrado(self, db_session: Session) -> None:
        """Jogo já encerrado não tem nomes/data_hora alterados."""
        # Cria rodada e jogo encerrado manualmente
        rodada = Rodada(nome="16-avos de final", ordem=4, aberta=False)
        db_session.add(rodada)
        db_session.flush()

        jogo = Jogo(
            rodada_id=rodada.id,
            espn_event_id="760486",
            data_hora=_DH_R32,
            time_casa="África do Sul",
            time_visitante="Canadá",
            gols_casa=2,
            gols_visitante=1,
            status=STATUS_ENCERRADO,
        )
        db_session.add(jogo)
        db_session.commit()

        # ESPN agora reporta times "diferentes" (não deve sobrescrever)
        evento = _evento_ko_real(nome_casa="South Africa Renamed")
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=[evento],
        ):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert resumo.jogos_atualizados_ko == 0
        db_session.refresh(jogo)
        assert jogo.time_casa == "África do Sul"  # não alterado

    def test_deadline_estourado_pula_busca(self, db_session: Session) -> None:
        """Se o deadline já estourou, retorna sem chamadas ESPN."""
        db_session.commit()

        mock_buscar = MagicMock()
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range", mock_buscar
        ), patch("app.services.sync_resultados.time.monotonic", return_value=1000.0):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA, deadline=10.0)

        mock_buscar.assert_not_called()
        assert resumo.jogos_criados == 0

    def test_erro_espn_nao_propaga(self, db_session: Session) -> None:
        """EspnClientError não deve propaghar — resumo volta zerado."""
        db_session.commit()

        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            side_effect=EspnClientError("timeout"),
        ):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert resumo.jogos_criados == 0

    def test_range_sem_eventos_ko_e_no_op(self, db_session: Session) -> None:
        """Payload apenas com jogos de fase de grupos: nenhuma rodada KO criada."""
        db_session.commit()

        evento_grupo = EventoEspn(
            abrev_casa="MEX",
            abrev_visitante="RSA",
            gols_casa=2,
            gols_visitante=0,
            status="STATUS_FULL_TIME",
            encerrado=True,
            estado="post",
            event_id="760415",
            season_slug="group-stage",  # NÃO é mata-mata
            data_hora=datetime(2026, 6, 11, 16, 0, 0, tzinfo=timezone.utc),
            nome_casa_espn="Mexico",
            nome_visitante_espn="South Africa",
        )
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=[evento_grupo],
        ):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert resumo.rodadas_criadas == 0
        assert resumo.jogos_criados == 0
        # Nenhuma rodada KO deve ter sido criada
        rodadas_ko = db_session.scalars(
            select(Rodada).where(Rodada.ordem >= 4)
        ).all()
        assert len(rodadas_ko) == 0

    def test_evento_sem_data_hora_nao_cria_jogo(self, db_session: Session) -> None:
        """Evento com data_hora=None não deve criar o jogo (não sabemos quando jogar)."""
        db_session.commit()

        evento = EventoEspn(
            abrev_casa="RSA",
            abrev_visitante="CAN",
            gols_casa=None,
            gols_visitante=None,
            status="STATUS_SCHEDULED",
            encerrado=False,
            estado="pre",
            event_id="760486",
            season_slug="round-of-32",
            data_hora=None,  # ausente
            nome_casa_espn="South Africa",
            nome_visitante_espn="Canada",
        )
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=[evento],
        ):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert resumo.jogos_criados == 0

    def test_multiplas_fases_criadas_de_uma_vez(self, db_session: Session) -> None:
        """Múltiplos slugs de mata-mata → múltiplas rodadas criadas."""
        db_session.commit()

        eventos = [
            _evento_ko_real(event_id="760001", slug="round-of-32"),
            _evento_ko_placeholder(event_id="760002", slug="round-of-16"),
        ]
        with patch(
            "app.services.sync_resultados.buscar_scoreboard_range",
            return_value=eventos,
        ):
            resumo = ingerir_jogos_mata_mata(db_session, _AGORA)

        assert resumo.rodadas_criadas == 2
        assert resumo.jogos_criados == 2

        r32 = db_session.scalar(select(Rodada).where(Rodada.ordem == 4))
        r16 = db_session.scalar(select(Rodada).where(Rodada.ordem == 5))
        assert r32 is not None
        assert r16 is not None


# ---------------------------------------------------------------------------
# Integração: sincronizar_resultados chama ingerir_jogos_mata_mata primeiro
# ---------------------------------------------------------------------------


class TestSincronizarResultadosIntegraMataMataSalvo:
    """Verifica que sincronizar_resultados chama ingerir_jogos_mata_mata e
    que os novos contadores aparecem no ResumoSync."""

    def test_contadores_ko_no_resumo_sync(self, db_session: Session) -> None:
        """Os campos rodadas_criadas/jogos_criados/jogos_atualizados_ko chegam no resumo."""
        db_session.commit()

        mock_ingerir = MagicMock(
            return_value=MagicMock(
                rodadas_criadas=2,
                jogos_criados=5,
                jogos_atualizados_ko=1,
            )
        )
        with patch(
            "app.services.sync_resultados.ingerir_jogos_mata_mata", mock_ingerir
        ), patch(
            "app.services.sync_resultados.buscar_scoreboard_com_janela",
            return_value=[],
        ):
            resumo = sincronizar_resultados(db_session, _AGORA)

        assert resumo.rodadas_criadas == 2
        assert resumo.jogos_criados == 5
        assert resumo.jogos_atualizados_ko == 1
        mock_ingerir.assert_called_once()

    def test_ingestao_ko_executada_antes_dos_resultados(self, db_session: Session) -> None:
        """ingerir_jogos_mata_mata deve ser chamado antes de buscar_scoreboard_com_janela."""
        chamadas: list[str] = []

        def fake_ingerir(db, agora, deadline=None):
            chamadas.append("ingerir")
            return MagicMock(rodadas_criadas=0, jogos_criados=0, jogos_atualizados_ko=0)

        def fake_buscar(data, deadline=None):
            chamadas.append("buscar")
            return []

        with patch("app.services.sync_resultados.ingerir_jogos_mata_mata", fake_ingerir), \
             patch(
                "app.services.sync_resultados.buscar_scoreboard_com_janela", fake_buscar
             ):
            sincronizar_resultados(db_session, _AGORA)

        # ingerir deve ter sido chamado; buscar pode ou não (depende de haver jogos pendentes)
        assert "ingerir" in chamadas
        if "buscar" in chamadas:
            assert chamadas.index("ingerir") < chamadas.index("buscar")


# ---------------------------------------------------------------------------
# Teste de migração: upgrade/downgrade
# ---------------------------------------------------------------------------


class TestMigracaoEspnEventId:
    """Verifica que a coluna espn_event_id existe no modelo e funciona corretamente."""

    def test_campo_espn_event_id_existe_no_modelo(self, db_session: Session) -> None:
        """Jogo pode ser criado com espn_event_id e recuperado por ele."""
        rodada = Rodada(nome="16-avos de final", ordem=4, aberta=False)
        db_session.add(rodada)
        db_session.flush()

        jogo = Jogo(
            rodada_id=rodada.id,
            espn_event_id="760486",
            data_hora=_DH_R32,
            time_casa="África do Sul",
            time_visitante="Canadá",
            status=STATUS_AGENDADO,
        )
        db_session.add(jogo)
        db_session.commit()

        recuperado = db_session.scalar(
            select(Jogo).where(Jogo.espn_event_id == "760486")
        )
        assert recuperado is not None
        assert recuperado.id == jogo.id

    def test_multiplos_null_nao_violam_unique(self, db_session: Session) -> None:
        """Múltiplos jogos com espn_event_id=None não violam a constraint UNIQUE."""
        rodada = Rodada(nome="Fase de Grupos", ordem=1, aberta=False)
        db_session.add(rodada)
        db_session.flush()

        for i in range(3):
            jogo = Jogo(
                rodada_id=rodada.id,
                espn_event_id=None,  # NULL não viola UNIQUE
                data_hora=datetime(2026, 6, 11 + i, 16, 0, 0, tzinfo=timezone.utc),
                time_casa=f"Time {i}",
                time_visitante=f"Visitante {i}",
                status=STATUS_AGENDADO,
            )
            db_session.add(jogo)

        db_session.commit()  # não deve levantar IntegrityError

        count = len(db_session.scalars(select(Jogo).where(Jogo.espn_event_id.is_(None))).all())
        assert count == 3

    def test_espn_event_id_unico_para_nao_null(self, db_session: Session) -> None:
        """Dois jogos com o mesmo espn_event_id não-None violam a constraint UNIQUE."""
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        rodada = Rodada(nome="16-avos de final", ordem=4, aberta=False)
        db_session.add(rodada)
        db_session.flush()

        jogo1 = Jogo(
            rodada_id=rodada.id,
            espn_event_id="760486",
            data_hora=_DH_R32,
            time_casa="África do Sul",
            time_visitante="Canadá",
            status=STATUS_AGENDADO,
        )
        db_session.add(jogo1)
        db_session.commit()

        jogo2 = Jogo(
            rodada_id=rodada.id,
            espn_event_id="760486",  # duplicado
            data_hora=_DH_R32,
            time_casa="Outro A",
            time_visitante="Outro B",
            status=STATUS_AGENDADO,
        )
        db_session.add(jogo2)
        with pytest.raises(SAIntegrityError):
            db_session.flush()
