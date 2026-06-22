"""Idempotência de credencial do importador (unit, sem depender do xlsx).

Garante que re-rodar o importador NÃO reescreve a senha de um usuário que já
existe (preserva a senha que o jogador trocou) nem rebaixa `is_admin`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Usuario
from app.services.auth import hash_senha, verificar_senha
from scripts.importar_planilha import _get_or_create_usuario


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
