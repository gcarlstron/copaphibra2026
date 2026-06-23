"""Idempotência de credencial do importador (unit, sem depender do xlsx).

Garante que re-rodar o importador NÃO reescreve a senha de um usuário que já
existe (preserva a senha que o jogador trocou) nem rebaixa `is_admin`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Rodada, Usuario
from app.services.auth import hash_senha, verificar_senha
from app.services.dashboard import STATUS_AGENDADO, STATUS_ENCERRADO
from scripts.importar_planilha import _get_or_create_jogo, _get_or_create_usuario


@pytest.fixture()
def db(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'imp.db'}",
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


def test_cria_usuario_novo_com_senha(db: Session) -> None:
    """Usuário novo é criado com a senha provisória."""
    usuario, criado = _get_or_create_usuario(db, "bernardo", "Bernardo", "senha_padrao")
    db.commit()
    assert criado is True
    assert verificar_senha("senha_padrao", usuario.senha_hash) is True


def test_rerun_nao_reescreve_senha_do_jogador(db: Session) -> None:
    """Re-rodar o importador preserva a senha que o jogador já trocou."""
    usuario, _ = _get_or_create_usuario(db, "bernardo", "Bernardo", "senha_padrao")
    db.commit()

    # Jogador troca a própria senha depois da carga inicial.
    usuario.senha_hash = hash_senha("minha_nova_senha")
    db.commit()

    # Re-import com a senha padrão NÃO pode sobrescrever a senha do jogador.
    usuario2, criado = _get_or_create_usuario(
        db, "bernardo", "Bernardo Silva", "senha_padrao"
    )
    db.commit()

    assert criado is False
    assert usuario2.id == usuario.id
    assert verificar_senha("minha_nova_senha", usuario2.senha_hash) is True
    assert verificar_senha("senha_padrao", usuario2.senha_hash) is False
    # Nome é re-sincronizado da planilha.
    assert usuario2.nome == "Bernardo Silva"


def test_rerun_nao_rebaixa_is_admin_nem_senha(db: Session) -> None:
    """Usuário existente com is_admin não é rebaixado nem tem a senha trocada."""
    existente = Usuario(
        nome="Chefe",
        username="gustavo",
        senha_hash=hash_senha("admin_pwd"),
        is_admin=True,
        ativo=True,
    )
    db.add(existente)
    db.commit()

    _, criado = _get_or_create_usuario(db, "gustavo", "Gustavo", "senha_padrao")
    db.commit()
    db.refresh(existente)

    assert criado is False
    assert existente.is_admin is True  # nunca rebaixado
    assert verificar_senha("admin_pwd", existente.senha_hash) is True
    assert verificar_senha("senha_padrao", existente.senha_hash) is False


def _seed_rodada(db: Session, ordem: int = 1) -> Rodada:
    rodada = Rodada(nome=f"{ordem}ª Rodada", ordem=ordem, aberta=False)
    db.add(rodada)
    db.commit()
    return rodada


def test_jogo_encerrado_nao_e_sobrescrito(db: Session) -> None:
    """Re-import NÃO sobrescreve um jogo já encerrado (resultado autoritativo)."""
    rodada = _seed_rodada(db)
    dh = datetime(2026, 6, 11, 16, 0, tzinfo=timezone.utc)

    jogo, criado, protegido = _get_or_create_jogo(
        db, rodada.id, "BRA", "ARG", dh, 2, 1, STATUS_ENCERRADO
    )
    db.commit()
    assert (criado, protegido) == (True, False)

    # Re-import com placar diferente NÃO pode sobrescrever.
    jogo2, criado2, protegido2 = _get_or_create_jogo(
        db, rodada.id, "BRA", "ARG", dh, 0, 0, STATUS_ENCERRADO
    )
    db.commit()
    assert (criado2, protegido2) == (False, True)
    assert jogo2.id == jogo.id
    assert (jogo2.gols_casa, jogo2.gols_visitante) == (2, 1)  # preservado


def test_jogo_agendado_ainda_recebe_resultado(db: Session) -> None:
    """Jogo ainda não encerrado é atualizado (sincroniza um resultado novo da planilha)."""
    rodada = _seed_rodada(db, ordem=2)
    dh = datetime(2026, 6, 12, 16, 0, tzinfo=timezone.utc)

    jogo, criado, protegido = _get_or_create_jogo(
        db, rodada.id, "FRA", "ESP", dh, None, None, STATUS_AGENDADO
    )
    db.commit()
    assert (criado, protegido) == (True, False)

    jogo2, criado2, protegido2 = _get_or_create_jogo(
        db, rodada.id, "FRA", "ESP", dh, 3, 0, STATUS_ENCERRADO
    )
    db.commit()
    assert (criado2, protegido2) == (False, False)
    assert (jogo2.gols_casa, jogo2.gols_visitante, jogo2.status) == (3, 0, STATUS_ENCERRADO)


def test_jogo_unique_constraint_rodada_times(db: Session) -> None:
    """Banco rejeita dois jogos com a mesma (rodada_id, time_casa, time_visitante)."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Jogo

    rodada = _seed_rodada(db, ordem=3)
    db.add(
        Jogo(
            rodada_id=rodada.id,
            data_hora=datetime(2026, 6, 13, 16, 0, tzinfo=timezone.utc),
            time_casa="BRA",
            time_visitante="ARG",
            status=STATUS_AGENDADO,
        )
    )
    db.commit()

    db.add(
        Jogo(
            rodada_id=rodada.id,
            data_hora=datetime(2026, 6, 13, 18, 0, tzinfo=timezone.utc),
            time_casa="BRA",
            time_visitante="ARG",
            status=STATUS_AGENDADO,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
